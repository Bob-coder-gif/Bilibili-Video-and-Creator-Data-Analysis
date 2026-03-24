from crawler.fetch_videos import fetch
from utils.file_utils import save_profile
from pathlib import Path

mid = 123456

profile = fetch(mid)

save_profile(profile, Path(f"data/cache/{mid}.json"))

print("完成！视频数量：", len(profile.videos))