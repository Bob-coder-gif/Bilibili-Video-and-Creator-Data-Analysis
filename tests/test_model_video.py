from datetime import datetime
from models.video import Video, VideoStats

video = Video(
    bvid="BV1xx",
    title="test",
    pubdate=datetime.now(),
    stats=VideoStats(view=100)
)

print(video)
print(video.pubdate_week)
print(video.to_dict())