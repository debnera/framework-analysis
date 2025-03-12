import zipfile


def get_folders(zip_file, size_limit_mb):
    if zip_file.endswith(".zip"):
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            items = zip_ref.namelist()
            json_files = [x for x in items if x.endswith('.json')]
            folders = {}
            for file in json_files:
                folder = os.path.dirname(file)
                if folder not in folders:
                    folders[folder] = []
                folders[folder].append(file)
    else:
        print(f"Cannot parse {zip_file}")

    return list(folders.values())