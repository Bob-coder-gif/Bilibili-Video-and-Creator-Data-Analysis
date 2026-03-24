import json
from pathlib import Path


def save_profile(profile, path: Path):
    '''
        with open(...) as f
            这种写法会自动管理文件资源，确保在使用完文件后正确关闭它，即使在过程中发生异常也能保证文件被关闭。
            "W"表示写入模式，如果文件不存在会创建，如果存在会覆盖。
    '''
    with open(path, "w", encoding="utf-8") as f:
        '''
            json.dump()函数将Python对象转换为JSON格式并写入文件。
            ensure_ascii=False参数确保非ASCII字符（如中文）能正确写入，而不是被转义为Unicode编码。
            indent=2参数使输出的JSON文件更易读，使用2个空格进行缩进。
        '''
        json.dump(profile.to_dict(), f, ensure_ascii=False, indent=2)


def load_profile(path: Path):
    from models.video import UploaderProfile
    
    '''
        with open(...) as f
            这种写法会自动管理文件资源，确保在使用完文件后正确关闭它，即使在过程中发生异常也能保证文件被关闭。
            "R"表示读取模式，如果文件不存在会抛出异常。
    '''
    with open(path, "r", encoding="utf-8") as f:
        '''
            json.load()函数从文件中读取JSON数据并将其转换为Python对象。
        '''
        data = json.load(f)

    return UploaderProfile.from_dict(data)