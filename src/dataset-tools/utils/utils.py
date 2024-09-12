import os

def list_zip_files(directory_path):
    zip_files = []
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith(".zip"):
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, directory_path)
                zip_files.append(relative_path)
    return zip_files