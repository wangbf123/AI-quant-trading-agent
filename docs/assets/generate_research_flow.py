"""Render repository-native GIF/PNG diagrams; no browser or external service.

Run with Pillow and Noto Sans CJK installed. The image illustrates architecture,
not a running experiment or measured market performance.
"""
from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
BOLD = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)

NODES = [
    (40, 200, '版本化数据', 'QLIB PROVIDER', '行情 · 日历 · 数据指纹', '#32c8b6'),
    (285, 200, '研究 Agent', 'REASON & PROPOSE', '假设 · 因子 · 实验规划', '#a5a1ff'),
    (530, 200, '确定性引擎', 'EXECUTE & VERIFY', 'Qlib · LightGBM · 成本', '#61adff'),
    (775, 200, '验证与证据', 'OBSERVE & COMPARE', '净收益 · 风险 · 消融', '#68d4e7'),
    (285, 393, '经济性失败记忆', 'REFLECT & RETRIEVE', '成本侵蚀 · 失效 · 上下文', '#c69bff'),
    (530, 393, '实验记录', 'PERSIST & REPRODUCE', 'SQL · Redis/RQ · 导出', '#8ba6cb'),
    (1020, 393, '封存样本外', 'FREEZE & FINALIZE', '固定候选 · 只评估一次', '#f5c477'),
]
EDGES = [
    ([(240,245),(285,245)],0,1),
    ([(485,245),(530,245)],1,2),
    ([(730,245),(775,245)],2,3),
    ([(875,290),(875,340),(385,340),(385,393)],3,4),
    ([(285,438),(262,438),(262,318),(385,318),(385,290)],4,1),
    ([(485,438),(530,438)],4,5),
    ([(975,245),(1120,245),(1120,393)],3,6),
]
STEPS = [0,1,2,3,4,1,5,6]
CAPTIONS = ['固定研究材料与执行假设','Agent 提出可检验的研究候选','确定性引擎训练、回测并计算成本','保留指标、负结果和实验轨迹','从验证失败中提取带上下文的证据','取回相关记忆，规划下一轮研究','保存数据、代码、配置与结果摘要','冻结后评估一次，最终结果不回流研究']

def point(points, fraction):
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
    distance=fraction*sum(lengths)
    for a,b,length in zip(points,points[1:],lengths):
        if distance<=length:
            t=distance/length
            return a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t
        distance-=length
    return points[-1]

def render(frame):
    image=Image.new('RGB',(1280,680),'#0b1121')
    draw=ImageDraw.Draw(image)
    for y in range(680):
        draw.line((0,y,1280,y),fill=(11+int(y/100),17+int(y/100),33+int(y/70)))
    for x in range(24,1280,24):
        for y in range(155,510,24):draw.ellipse((x,y,x+1,y+1),fill='#23304b')
    step=(frame//12)%len(STEPS)
    active=STEPS[step]
    draw.text((40,27),'AGENTIC QUANT RESEARCH PLATFORM',font=font(14),fill='#8496bc')
    draw.text((40,59),'让研究可解释，让结论可验证。',font=font(32,True),fill='#ecf1ff')
    draw.text((42,117),CAPTIONS[step],font=font(18),fill='#9caad0')
    draw.rounded_rectangle((1030,38,1240,75),radius=18,fill='#19243a',outline='#2e3d59')
    draw.text((1051,45),'流程示意 / 非实时实验',font=font(13),fill='#9facc5')
    draw.text((290,171),'研究决策',font=font(12),fill='#a5a1ff')
    draw.text((535,171),'执行验证',font=font(12),fill='#61adff')
    for points,source,target in EDGES:
        highlighted=active in (source,target)
        color=NODES[active][5] if highlighted else '#34425c'
        draw.line(points,fill=color,width=2,joint='curve')
        end=points[-1];prev=points[-2]
        angle=math.atan2(end[1]-prev[1],end[0]-prev[0])
        arrow=[end]+[(end[0]-8*math.cos(angle+a),end[1]-8*math.sin(angle+a)) for a in (-.5,.5)]
        draw.polygon(arrow,fill=color)
        if highlighted:
            x,y=point(points,(frame%12)/12)
            draw.ellipse((x-4,y-4,x+4,y+4),fill=color)
    for index,(x,y,title,en,sub,color) in enumerate(NODES):
        selected=index==active
        draw.rounded_rectangle((x,y,x+200,y+90),radius=12,fill='#151e32',outline=color if selected else '#2c3951',width=2 if selected else 1)
        draw.text((x+15,y+12),en,font=font(9),fill=color)
        draw.text((x+15,y+30),title,font=font(19,True),fill='#ecf0ff')
        draw.text((x+15,y+63),sub,font=font(11),fill='#93a2bf')
    draw.text((810,310),'验证反馈',font=font(12),fill='#93a2bf')
    draw.text((1022,498),'最终结果禁止回流记忆',font=font(12),fill='#f5c477')
    draw.line((40,539,1240,539),fill='#2b3750')
    labels=[('TRAIN / 训练','#61adff'),('TUNE / 调参','#a5a1ff'),('VALIDATION / 研究验证','#c69bff'),('HOLDOUT / 最终封存','#f5c477')]
    for i,(label,color) in enumerate(labels):
        x=40+i*305
        draw.rounded_rectangle((x,563,x+275,598),radius=6,fill='#182238')
        draw.rectangle((x,563,x+3,598),fill=color)
        draw.text((x+13,570),label,font=font(12),fill=color)
        if i<3:draw.text((x+277,576),'//',font=font(12),fill='#657797')
    draw.text((40,625),'QuantaAlpha 基座  +  Qlib 验证  +  经济性失败记忆',font=font(12),fill='#8b9abb')
    draw.text((833,625),'窗口之间 purge ≥ 2 个交易日',font=font(12),fill='#8b9abb')
    return image

if __name__=='__main__':
    frames=[render(i) for i in range(96)]
    frames[12].save(ROOT/'research-flow.png')
    palette=frames[12].quantize(colors=128)
    frames=[frame.quantize(palette=palette,dither=Image.Dither.NONE) for frame in frames]
    frames[0].save(ROOT/'research-flow.gif',save_all=True,append_images=frames[1:],duration=100,loop=0,optimize=True,disposal=2)
    print('Generated 96-frame architecture GIF and static PNG')
