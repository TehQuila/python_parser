def qual_name_from_path(path, file=None):
    name = path.replace('/', '.')
    if file:
        name += '.' + file.split('.')[0]
    return name
