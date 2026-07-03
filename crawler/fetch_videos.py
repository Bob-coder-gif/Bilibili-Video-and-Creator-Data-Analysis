from models.video import Video, VideoStats, UploaderProfile
from datetime import datetime

import models.video
from utils.log_utils import get_logger

logger = get_logger()

# 排查 import 路径问题时加的调试信息，平时不需要看，改为 debug
logger.debug(f"models.video 模块加载自: {models.video.__file__}")


def fetch(mid: int) -> UploaderProfile:
    profile = UploaderProfile(mid=mid, name="test")

    # 假数据（后面换API）   目前仅用于前期测试
    raw_videos = [
        {
            "bvid": "BV1",
            "title": "视频1",
            "pubdate": 1700000000,
            "view": 1000
        },
        {
            "bvid": "BV2",
            "title": "视频2",
            "pubdate": 1700000000,
            "view": 1000
        }
    ]

    for item in raw_videos:
        video = Video(
            bvid=item["bvid"],
            title=item["title"],
            pubdate=datetime.fromtimestamp(item["pubdate"]),
            stats=VideoStats(
                view=item.get("view", 0),
                like=item.get("like", 0),
                coin=item.get("coin", 0),
                collect=item.get("collect", 0),
                danmaku=item.get("danmaku", 0),
            )
        )
        profile.add_video(video)

    profile.sort_videos()

    return profile