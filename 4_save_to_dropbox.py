import argparse
import os
import subprocess
import dropbox
from dotenv import load_dotenv


def upload_via_rclone(file_path, dest_path):
    """Uploads a file using rclone."""
    try:
        file_name = os.path.basename(file_path)
        full_dest = f"{dest_path.rstrip('/')}/{file_name}"

        result = subprocess.run(
            ["rclone", "copyto", file_path, full_dest],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print(f"Successfully uploaded {file_name} via rclone to: {full_dest}")
            return True
        else:
            print(f"*** rclone error: {result.stderr}")
            return False
    except FileNotFoundError:
        print("*** Error: rclone is not installed or not in PATH")
        return False
    except Exception as e:
        print(f"*** Error uploading {file_path} via rclone: {e}")
        return False


def upload_to_dropbox(file_path, dbx):
    """Uploads a file to Dropbox via API."""
    try:
        file_name = os.path.basename(file_path)
        dropbox_path = f"/{file_name}"
        with open(file_path, "rb") as f:
            # Check file size, if > 150MB, use upload_session
            if os.path.getsize(file_path) > 150 * 1024 * 1024:
                print(f"File {file_name} is larger than 150MB, using chunked upload.")
                upload_session_start_result = dbx.files_upload_session_start(f.read(150 * 1024 * 1024))
                cursor = dropbox.files.UploadSessionCursor(session_id=upload_session_start_result.session_id,
                                                           offset=f.tell())
                commit = dropbox.files.CommitInfo(path=dropbox_path, mode=dropbox.files.WriteMode('overwrite'))

                while f.tell() < os.path.getsize(file_path):
                    if (os.path.getsize(file_path) - f.tell()) <= 150 * 1024 * 1024:
                        dbx.files_upload_session_finish(f.read(150 * 1024 * 1024), cursor, commit)
                    else:
                        dbx.files_upload_session_append_v2(f.read(150 * 1024 * 1024), cursor)
                        cursor.offset = f.tell()
            else:
                 dbx.files_upload(f.read(), dropbox_path, mode=dropbox.files.WriteMode('overwrite'))

        print(f"Successfully uploaded {file_name} to Dropbox path: {dropbox_path}")
    except dropbox.exceptions.ApiError as err:
        print(f"*** Dropbox API error: {err}")
        return None
    except Exception as e:
        print(f"*** Error uploading {file_path}: {e}")
        return None


def main():
    """Main function to handle argument parsing and file uploads."""
    # Load environment variables from .env file
    load_dotenv()

    # Check for rclone configuration
    rclone_md_dest = os.getenv("RCLONE_MD_DEST")
    rclone_pdf_dest = os.getenv("RCLONE_PDF_DEST")
    use_rclone = rclone_md_dest or rclone_pdf_dest

    # Setup argument parser
    parser = argparse.ArgumentParser(description="Upload files to Dropbox.")
    parser.add_argument('files', nargs='+', help='List of files to upload.')
    args = parser.parse_args()

    # Use rclone if configured
    if use_rclone:
        print("Using rclone for upload...")
        for file_path in args.files:
            if not os.path.exists(file_path):
                print(f"File not found: {file_path}")
                continue

            # Determine destination based on file extension
            if file_path.endswith('.md'):
                if rclone_md_dest:
                    upload_via_rclone(file_path, rclone_md_dest)
                else:
                    print(f"Skipping {file_path}: RCLONE_MD_DEST not configured")
            elif file_path.endswith('.pdf'):
                if rclone_pdf_dest:
                    upload_via_rclone(file_path, rclone_pdf_dest)
                else:
                    print(f"Skipping {file_path}: RCLONE_PDF_DEST not configured")
            else:
                # For other file types, use MD dest as default, or PDF dest as fallback
                dest = rclone_md_dest or rclone_pdf_dest
                upload_via_rclone(file_path, dest)
        return

    # Fall back to Dropbox API
    app_key = os.getenv("DROPBOX_APP_KEY")
    app_secret = os.getenv("DROPBOX_APP_SECRET")
    refresh_token = os.getenv("DROPBOX_REFRESH_TOKEN")

    if not all([app_key, app_secret, refresh_token]):
        print("Error: Either configure RCLONE_MD_DEST/RCLONE_PDF_DEST for rclone, or DROPBOX_APP_KEY, DROPBOX_APP_SECRET, and DROPBOX_REFRESH_TOKEN for Dropbox API.")
        return

    try:
        dbx = dropbox.Dropbox(
            app_key=app_key,
            app_secret=app_secret,
            oauth2_refresh_token=refresh_token
        )
        dbx.users_get_current_account()
        print("Successfully connected to Dropbox.")
    except Exception as e:
        print(f"Error connecting to Dropbox: {e}")
        return

    for file_path in args.files:
        if os.path.exists(file_path):
            upload_to_dropbox(file_path, dbx)
        else:
            print(f"File not found: {file_path}")

if __name__ == "__main__":
    main() 