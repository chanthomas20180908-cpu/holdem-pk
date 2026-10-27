"""Seat-specific hosting guidance, not an automated action policy."""
PROFILES = (
    ('施压', '偏向开池、隔离和挤压；弱牌需要位置、阻断或对手弃牌倾向支持；强牌也可跟注。'),
    ('设局', '偏向保护过牌和跟注范围；会慢打强牌，也会延迟下注偷池，不把过牌等同放弃。'),
    ('换挡', '宽范围争夺位置；可用听牌半诈唬、选择性多轮施压，遇到强烈反击及时收手。'),
    ('抓诈唬', '观察公开下注线，适度用中等牌力抓诈唬；也会薄价值下注，不无条件跟到底。'),
    ('搅局', '主动偷盲、挤压与反偷；同样尺度同时用于价值与诈唬，保留强牌跟注线。'),
    ('读局', '重视位置与范围变化；可用阻断牌加注、用强牌过牌，避免机械持续下注。'),
    ('诱导', '偏向跟注入局和诱导；合适时主动大额价值下注或有依据地诈唬，避免只跟不加。'),
)


def profile(seat):
    label, guidance = PROFILES[(seat - 1) % len(PROFILES)]
    return dict(style=label, guidance=guidance, protocol='GAMBLER.md', version=1)
