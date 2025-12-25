import math
import ezdxf
import ezdxf.path
from ezdxf.math import Vec2
from dataclasses import dataclass


# 定义一个简单的设备数据结构
@dataclass
class DeviceRecord:
    index: int
    name: str  # 块名
    station_str: str  # 格式化桩号 (K12+345)
    station_val: float  # 数值桩号 (12345.0)
    side: str  # Left / Right
    offset: float  # 距离中心线的距离
    x: float
    y: float


class LegacyRouteCalculator:
    """
    核心路由计算器 (升级版)
    增加了 project_point 方法：将任意坐标投影到中心线上，获取桩号和偏距
    """

    def __init__(self, entity, step_precision=0.5):
        # 1. 转为 Path 并打散
        self.path_obj = ezdxf.path.make_path(entity)
        # flattening 得到的是密集的顶点列表
        self.vertices = list(self.path_obj.flattening(distance=step_precision))

        # 2. 预计算每一段的长度和累计桩号
        self.dists = [0.0]  # 每个点的累计桩号 [0, 1.2, 2.5 ...]
        self.segments = []  # 存储线段向量，加速计算

        for i in range(1, len(self.vertices)):
            p_prev = self.vertices[i - 1]
            p_curr = self.vertices[i]

            seg_len = p_prev.distance(p_curr)
            cumulative = self.dists[-1] + seg_len

            self.dists.append(cumulative)
            self.segments.append({
                'p1': p_prev,
                'p2': p_curr,
                'len': seg_len,
                'start_dist': self.dists[i - 1],
                'vec': p_curr - p_prev  # 预计算向量
            })

        self.total_length = self.dists[-1]

    def project_point(self, target_point: Vec2):
        """
        核心算法：将外部点投影到最近的中心线段上
        返回: (station, offset, side_str)
        """
        min_dist = float('inf')
        best_station = 0.0
        best_side = "Center"

        # 遍历所有微元线段，寻找最近点
        # (注：对于超长公路，这里可以用 R-Tree 空间索引优化，但对于几百个设备，暴力遍历足够快)
        for seg in self.segments:
            p1 = seg['p1']
            vec_seg = seg['vec']  # 线段向量
            seg_len_sq = vec_seg.magnitude_xy  # 长度平方

            if seg_len_sq == 0: continue

            # 向量投影: 计算点 P 在线段 AB 上的投影比例 t
            # t = (AP · AB) / |AB|^2
            vec_pt = target_point - p1
            t = vec_pt.dot(vec_seg) / seg_len_sq

            # 限制 t 在 [0, 1] 之间（夹在端点内）
            t_clamped = max(0.0, min(1.0, t))

            # 计算投影点坐标
            projected_p = p1 + vec_seg * t_clamped

            # 计算垂直距离 (Offset)
            dist = target_point.distance(projected_p)

            if dist < min_dist:
                min_dist = dist

                # 1. 计算桩号
                best_station = seg['start_dist'] + (t_clamped * seg['len'])

                # 2. 判断左右侧 (使用二维叉乘)
                # 叉乘: A x B = x1*y2 - x2*y1
                # 如果结果 > 0，点在向量左侧；< 0 在右侧 (取决于坐标系，CAD通常遵循右手定则)
                cross_product = vec_seg.x * vec_pt.y - vec_seg.y * vec_pt.x
                best_side = "左幅外侧" if cross_product > 0 else "右幅外侧"

        return best_station, min_dist, best_side


class RouteCalculator:
    """
    核心路由计算器 (定距逻辑版 - 修复 Vec2 属性报错)
    """

    def __init__(self, entity, start_PK="K0+000"):
        # 0. 解析起始桩号
        self.base_offset = self._parse_pk_string(start_PK)

        # 1. 提取顶点
        raw_points = []
        if entity.dxftype() == 'LWPOLYLINE':
            raw_points = entity.get_points(format='xy')
        elif entity.dxftype() == 'LINE':
            raw_points = [entity.dxf.start, entity.dxf.end]
        else:
            raise TypeError("RouteCalculator 输入必须是 LWPOLYLINE 或 LINE")

        # 2. 预计算每一段
        self.segments = []

        for i in range(len(raw_points) - 1):
            # 强制转为 Vec2
            p_prev = Vec2(raw_points[i])
            p_curr = Vec2(raw_points[i + 1])

            vec = p_curr - p_prev

            # --- 核心修复：手动计算长度平方 ---
            # 某些版本的 ezdxf Vec2 没有 magnitude_sq 属性
            # 我们直接用 x*x + y*y 代替，效果完全一样且更快
            len_sq = vec.x * vec.x + vec.y * vec.y

            start_stat = self.base_offset + (i * 100.0)

            self.segments.append({
                'p1': p_prev,
                'p2': p_curr,
                'vec': vec,
                'len_sq': len_sq,  # <--- 这里使用了修复后的变量
                'start_stat': start_stat,
                'logic_span': 100.0
            })

        self.total_length = self.segments[-1]['start_stat'] + 100.0

    def _parse_pk_string(self, pk_str):
        if isinstance(pk_str, (int, float)):
            return float(pk_str)
        clean_str = pk_str.upper().replace('K', '').replace(' ', '')
        if '+' in clean_str:
            try:
                parts = clean_str.split('+')
                return float(parts[0]) * 1000 + float(parts[1])
            except ValueError:
                return 0.0
        try:
            return float(clean_str)
        except ValueError:
            return 0.0

    def project_point(self, target_point: Vec2):
        min_dist = float('inf')
        best_station = 0.0
        best_side = "Center"

        for seg in self.segments:
            p1 = seg['p1']
            vec_seg = seg['vec']
            seg_len_sq = seg['len_sq']

            if seg_len_sq == 0:
                t_clamped = 0.0
            else:
                vec_pt = target_point - p1
                # 向量点积：x1*x2 + y1*y2
                t = vec_pt.dot(vec_seg) / seg_len_sq
                t_clamped = max(0.0, min(1.0, t))

            projected_p = p1 + vec_seg * t_clamped
            dist = target_point.distance(projected_p)

            if dist < min_dist:
                min_dist = dist
                best_station = seg['start_stat'] + (t_clamped * seg['logic_span'])
                cross_product = vec_seg.x * vec_pt.y - vec_seg.y * vec_pt.x
                best_side = "左幅外侧" if cross_product > 0 else "右幅外侧"

        return best_station, min_dist, best_side


class DeviceLayoutEngine:
    def __init__(self, dxf_path, centerline_layer="ROAD_CENTER"):
        print(f"正在加载 CAD 文件: {dxf_path} ...")
        self.doc = ezdxf.readfile(dxf_path)
        self.msp = self.doc.modelspace()
        self.centerline_layer = centerline_layer

        # 初始化路由计算器
        self.route = self._init_route()
        print(f"中心线解析完成，全长: {self.route.total_length:.2f}m")

    def _init_route(self):
        """获取中心线并构建计算器"""
        polylines = self.msp.query(f'LWPOLYLINE[layer=="{self.centerline_layer}"]')
        if not polylines:
            raise ValueError(f"未找到中心线图层: {self.centerline_layer}")

        # 取最长的一条
        target_pl = max(polylines, key=lambda e: len(e))
        return RouteCalculator(target_pl)

    def format_station(self, station_val):
        """将 12345.67 格式化为 K12+345.67"""
        km = int(station_val // 1000)
        m = int(station_val % 1000)
        return f"K{km}+{m:03d}"

    def extract_and_project_devices(self, target_block_names=None):
        """
        读取所有 INSERT 实体，过滤出指定的设备块，并计算桩号
        :param target_block_names: dict, 例如 ['CCTV': '中文名称', 'VMS': '中文名称', 'Camera': '中文名称']，为 None 则提取所有块
        """
        devices = []
        index = 1

        # 查询所有块引用
        inserts = self.msp.query('INSERT')

        print(f"共发现 {len(inserts)} 个图块，正在筛选并计算投影...")

        for entity in inserts:
            block_name = entity.dxf.name

            # 过滤块名
            if target_block_names and block_name not in target_block_names.keys():
                continue

            # 获取插入点 (Vec2)
            insert_pos = Vec2(entity.dxf.insert.x, entity.dxf.insert.y)

            # --- 核心调用：投影计算 ---
            station, offset, side = self.route.project_point(insert_pos)

            # 记录数据
            rec = DeviceRecord(
                index=index,
                name=target_block_names[block_name],
                station_str=self.format_station(station),
                station_val=station,
                side=side,
                offset=round(offset, 3),  # 保留3位小数
                x=round(insert_pos.x, 3),
                y=round(insert_pos.y, 3)
            )
            devices.append(rec)
            index += 1

        # 按桩号排序 (从小到大)
        devices.sort(key=lambda d: d.station_val)

        # 重新生成序号
        for i, d in enumerate(devices):
            d.index = i + 1

        print(f"✅ 处理完成，共提取有效设备 {len(devices)} 个")
        return devices