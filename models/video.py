from dataclasses import dataclass, field,asdict
from typing import List, Tuple,Optional
from datetime import datetime

#单视频统计数据
@dataclass
class VideoStats:
    view: int = 0
    like: int = 0
    coin: int = 0
    collect: int = 0
    danmaku: int = 0

    #接收外部数据，将外部数据（如字典）转换为VideoStats对象
    @staticmethod
    def from_dict(data: dict):
        return VideoStats(
            videw=data.get('videw', 0),
            like=data.get('like', 0),
            coin=data.get('coin', 0),
            collect=data.get('collect', 0),
            danmaku=data.get('danmaku', 0)
        )   
    
    #将VideoStats对象转换为字典，以便于序列化或其他用途
    def to_dict(self):
        return asdict(self)
        


#视频实体
@dataclass
class Video:
    bvid: str    #bilibili video id
    title: str
    pubdate: datetime
    stats: VideoStats

    #@dataclass不支持直接计算属性，所以使用field(init=False)来定义一个不参与初始化的属性
    pubdate_week: str = field(init=False)
    '''init = False 告诉@dataclass 不要把这个字段放入自动生成的__init__方法中，
        结果：当创建对象时，不需要（也不能）提供这个字段的值，且这个字段不会被自动赋值。
        目的：这个字段的值将由类自己在内部计算生成，而不是由外部提供。
    '''

    #__post_init__是@dataclass提供的一个特殊方法，在对象初始化完成后自动调用
    def __post_init__(self):
        #转换为ISO周格式，例如：2024-W24
        year, week, _ = self.pubdate.isocalendar()
        self.pubdate_week = f"{year}-W{week:02d}"

    @staticmethod
    def from_dict(data: dict):
        return Video(
            bvid=data['bvid'],
            title=data['title'],
            pubdate=datetime.fromisoformat(data['pubdate']),
            stats=VideoStats.from_dict(data['stats'])
        )
    
    def to_dict(self):
        return {
            'bvid': self.bvid,
            'title': self.title,
            'pubdate': self.pubdate.isoformat(),
            'pubdate_week': self.pubdate_week,
            'stats': self.stats.to_dict()
        }
    

#up主整体数据
@dataclass
class UploaderProfile:
    mid: int   #up主id   member id
    name: str

    videos: List[Video] = field(default_factory=list)
    '''
        default_factory=list 告诉@dataclass 在创建对象时，
        如果没有提供videos参数，就使用一个新的空列表作为默认值。
        目的：避免多个对象共享同一个列表实例，确保每个对象都有自己的独立列表。
            ps:py中默认参数如果是可变对象（如列表、字典等）
            ，会在函数定义时创建一次，并被所有调用共享。
        结果：这样每次构建新的实例时都贵调用list()来创建一个新的空列表，
            确保每个up实例都有自己的独立列表。
    '''

    #(时间戳，粉丝数)列表
    followers_history: List[Tuple[datetime, int]] = field(default_factory=list)    

    def add_video(self, video: Video):
        self.videos.append(video)

    def add_follower_snapshot(self, time: datetime, followers: int):
        self.followers_history.append((time, followers))

    def sort_videos(self):
        self.videos.sort(key=lambda v: v.pubdate)
    '''
        lambda v: v.pubdate 是一个匿名函数，接受一个视频对象v，并返回它的pubdate属性。
        key=lambda v: v.pubdate 告诉sort方法根据视频的发布时间来排序
    '''

    def to_dict(self):
        return {
            'mid': self.mid,
            'name': self.name,
            'videos': [video.to_dict() for video in self.videos],
            'followers_history': [(time.isoformat(), followers) for time, followers in self.followers_history]
        }
    
    @staticmethod
    def from_dict(data: dict):
        profile = UploaderProfile(
            mid=data['mid'],
            name=data['name',""]
        )

        profile.videos = [Video.from_dict(video_data) for video_data in data.get('videos', [])]
        profile.followers_history = [
            (datetime.fromisoformat(time_str), followers) 
            for time_str, followers in data.get('followers_history', [])
            ]
        return profile