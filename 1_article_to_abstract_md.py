#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
from datetime import datetime
from dotenv import load_dotenv
import time
from threading import Lock
from pathlib import Path
import re

try:
    from openai import OpenAI
except ImportError:
    print("请先安装相应的 SDK, 例如: pip install openai 或检查引用。")
    sys.exit(1)

# 速率限制器实现
class RateLimiter:
    def __init__(self, max_per_minute=1000):
        self.max_per_minute = max_per_minute
        self.minute_count = 0
        self.last_reset_minute = time.time()
        self.lock = Lock()
        
    def acquire(self):
        with self.lock:
            current_time = time.time()
            
            # 检查是否需要重置分钟计数器
            if current_time - self.last_reset_minute >= 60:
                self.minute_count = 0
                self.last_reset_minute = current_time
            
            # 检查是否超过限制
            if self.minute_count >= self.max_per_minute:
                sleep_time = 60 - (current_time - self.last_reset_minute)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                self.minute_count = 0
                self.last_reset_minute = time.time()
            
            # 增加计数器
            self.minute_count += 1

# 创建全局限流器
rate_limiter = RateLimiter()

def generate_abstract_from_article(client, model_id, article_path, batch_idx, progress_callback=None):
    """
    用于并行调用 API 的辅助函数：
    给定 client, model_id, article_path, 调用接口获取对应 Markdown 摘要。
    
    包含重试逻辑：如果发生错误，会自动重试最多3次。
    超过重试次数后，对错误情况返回None。
    
    返回值： (idx, md_text 或 None, 错误信息或 None)
    """
    MAX_RETRIES = 3
    retry_count = 0
    
    # 读取文章内容
    try:
        with open(article_path, 'r', encoding='utf-8') as f:
            article_content = f.read()
    except Exception as e:
        error_message = f"无法读取文章文件 {article_path}: {str(e)}"
        print(error_message)
        if progress_callback:
            progress_callback(error_message)
        return (batch_idx, None, error_message)
    
    # 读取系统提示文件
    with open('./system_prompt/abstract_prompt.md', 'r', encoding='utf-8') as f:
        prompt = f.read()
    
    while retry_count < MAX_RETRIES:
        try:
            # 获取速率限制许可
            rate_limiter.acquire()
            
            completion = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": article_content},
                ],
                temperature=0.5
            )
            # 无调试输出，保持日志干净
            # 兼容不同提供方在 content 字段的返回（可能为 str 或 list[{"type":"text","text":...}])
            choice = completion.choices[0]
            msg = choice.message
            md_text = getattr(msg, "content", None)
            if isinstance(md_text, list):
                try:
                    md_text = "".join([
                        (part.get("text") if isinstance(part, dict) else getattr(part, "text", ""))
                        for part in md_text
                    ])
                except Exception:
                    # 兜底：转为 dict 再取
                    data = completion.model_dump() if hasattr(completion, "model_dump") else {}
                    parts = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", [])
                    )
                    md_text = "".join([p.get("text", "") for p in parts if isinstance(p, dict)])
            elif md_text is None:
                # 兜底处理 None
                data = completion.model_dump() if hasattr(completion, "model_dump") else {}
                val = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content")
                )
                if isinstance(val, list):
                    md_text = "".join([p.get("text", "") for p in val if isinstance(p, dict)])
                else:
                    md_text = (val or "")

            # 规范化输出：
            # 1) 去除可能的代码块围栏 ``` 或 ```markdown
            if md_text.strip().startswith("```"):
                # 去掉首尾围栏
                md_text = re.sub(r"^```[a-zA-Z]*\n?", "", md_text.strip())
                md_text = re.sub(r"\n?```\s*$", "", md_text)
            # 2) 如果包含 #，保留从第一个 # 开始，避免模型在前面添加说明
            if "#" in md_text and not md_text.lstrip().startswith('#'):
                start_hash = md_text.find('#')
                if start_hash != -1:
                    md_text = md_text[start_hash:]
            md_text = md_text.strip()
            # 结束：返回标准化后的摘要文本
            
            return (batch_idx, md_text, None)
        
        except Exception as e:
            error_msg = str(e)
            retry_count += 1
            
            retry_error_message = f"Article#{batch_idx}: API调用出错: {error_msg}，正在重试 ({retry_count}/{MAX_RETRIES})..."
            print(retry_error_message)
            if progress_callback:
                progress_callback(retry_error_message)
            
            if retry_count < MAX_RETRIES:
                time.sleep(1)  # 延迟一秒后重试
            else:
                final_error_message = f"Article#{batch_idx}: 已达到最大重试次数，放弃处理此文章..."
                print(final_error_message)
                if progress_callback:
                    progress_callback(final_error_message)
                return (batch_idx, None, error_msg)


def main(input_articles_file, output_md=None, progress_callback=None):
    """
    从input_articles_file文件读取文章路径列表，利用多线程并行调用AI生成摘要Markdown文本并合并，
    最终输出为一个output_md文件（纯Markdown）。
    从环境变量或.env文件读取API Key、model ID和处理参数。
    
    如果未指定output_md，则使用默认路径和文件名：./abstract_md/abstract_md_yyyymmdd_hhmmss.md
    
    参数:
        input_articles_file: 包含文章路径列表的输入文件
        output_md: 输出Markdown文件路径
        progress_callback: 进度回调函数，用于实时更新进度信息
    """
    # 如果未指定输出文件，则使用默认路径和文件名
    if output_md is None:
        # 确保输出目录存在
        script_dir = Path(__file__).parent
        output_dir = script_dir / "abstract_md"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 生成带时间戳的文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_md = str(output_dir / f"abstract_md_{timestamp}.md")

    # 从.env文件加载环境变量
    load_dotenv()
    
    # 使用 Gemini 端点与模型（OpenAI 兼容接口）。
    # 模型：优先从 Gemini_ABSTRACT_MODEL_ID 读取；未设置则回退到 Gemini_MODEL_ID；仍未设置则默认 gemini-2.5-flash。
    api_key = os.getenv("Gemini_API_KEY")
    model_id = (
        os.getenv("Gemini_ABSTRACT_MODEL_ID")
        or os.getenv("Gemini_MODEL_ID")
        or "gemini-2.5-flash"
    )
    base_url = os.getenv("Gemini_BASE_URL")
    
    # 并发线程数，可通过环境变量覆盖，默认20
    try:
        max_workers = int(os.getenv("ABSTRACT_MAX_WORKERS", "20"))
    except ValueError:
        max_workers = 20
    batch_size = max_workers
    
    if not api_key:
        message = "未找到 Gemini_API_KEY 环境变量，请检查 .env 文件！"
        print(message)
        if progress_callback:
            progress_callback(message)
        sys.exit(1)
    
    if not base_url:
        message = "未找到 Gemini_BASE_URL 环境变量，请检查 .env 文件！"
        print(message)
        if progress_callback:
            progress_callback(message)
        sys.exit(1)

    # 初始化客户端
    client = OpenAI(base_url=base_url, api_key=api_key)

    # 读取包含文章路径的文件
    if not os.path.exists(input_articles_file):
        message = f"输入文件 {input_articles_file} 不存在！"
        print(message)
        if progress_callback:
            progress_callback(message)
        sys.exit(1)

    with open(input_articles_file, "r", encoding="utf-8") as f:
        article_paths = [line.strip() for line in f if line.strip()]

    total_articles = len(article_paths)
    total_batches = math.ceil(total_articles / batch_size)
    message = f"\n开始处理，共{total_articles}篇文章，分{total_batches}批进行（每批{batch_size}篇）...\n"
    print(message)
    if progress_callback:
        progress_callback(message)

    # 并行调用 API
    results = []  # 用于存放 (idx, md_text) 的结果
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for batch in range(total_batches):
            start_idx = batch * batch_size
            end_idx = min((batch + 1) * batch_size, total_articles)
            batch_articles = article_paths[start_idx:end_idx]
            current_batch_size = len(batch_articles)
            remaining_batches = total_batches - batch - 1
            
            message = f"正在处理第{batch+1}批，共{current_batch_size}篇文章，还剩{remaining_batches}批"
            print(message)
            if progress_callback:
                progress_callback(message)
            
            future_to_idx = {}
            for i, article_path in enumerate(batch_articles):
                future = executor.submit(
                    generate_abstract_from_article, 
                    client, 
                    model_id, 
                    article_path, 
                    start_idx+i, 
                    progress_callback
                )
                future_to_idx[future] = start_idx+i

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    (ret_idx, md_text, err_msg) = future.result()
                    if err_msg:
                        error_message = f"错误: {err_msg}"
                        print(error_message)
                        if progress_callback:
                            progress_callback(error_message)
                        continue
                    results.append((ret_idx, md_text))
                except Exception as e:
                    error_message = f"错误: {e}"
                    print(error_message)
                    if progress_callback:
                        progress_callback(error_message)

            batch_complete_message = f"第{batch+1}批处理完成"
            print(batch_complete_message)
            if progress_callback:
                progress_callback(batch_complete_message)

    completion_message = f"\n全部处理完成，成功处理 {len(results)}/{total_articles} 篇文章\n"
    print(completion_message)
    if progress_callback:
        progress_callback(completion_message)

    # 按照原先顺序 (idx) 排序并合并所有 Markdown
    results.sort(key=lambda x: x[0])
    merged_md = "\n\n".join((r[1].strip() if r[1] else "") for r in results if r[1] and r[1].strip())

    if not merged_md.strip():
        empty_message = "未获取到任何有效内容，程序结束。"
        print(empty_message)
        if progress_callback:
            progress_callback(empty_message)
        return

    # 将合并后的 Markdown 内容写入 .md 文件
    try:
        # 确保输出目录存在
        output_dir = os.path.dirname(output_md)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        with open(output_md, "w", encoding="utf-8") as f:
            f.write(merged_md)
        file_message = f"已生成Markdown文件：{output_md}"
        print(file_message)
        if progress_callback:
            progress_callback(file_message)
        return output_md
    except Exception as e:
        error_message = f"写入文件失败: {e}"
        print(error_message)
        if progress_callback:
            progress_callback(error_message)

if __name__ == "__main__":
    """
    命令行用法示例:
        python 1b_article_to_abstract_md.py successful_articles.txt [output.md]
        
    如果不指定输出文件，则使用默认路径和文件名：./abstract_md/abstract_md_yyyymmdd_hhmmss.md
    """
    if len(sys.argv) < 2:
        print("用法示例: python 1b_article_to_abstract_md.py successful_articles.txt [output.md]")
        print("如果不指定输出文件，则使用默认路径和文件名：./abstract_md/abstract_md_yyyymmdd_hhmmss.md")
        sys.exit(1)

    input_articles_file = sys.argv[1]
    output_md_path = sys.argv[2] if len(sys.argv) > 2 else None
    main(input_articles_file, output_md_path) 
