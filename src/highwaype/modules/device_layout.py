import math
import ezdxf
import ezdxf.path
from ezdxf.addons import Importer
from ezdxf.math import Vec2
from dataclasses import dataclass
# 增加文字对齐枚举
from ezdxf.enums import TextEntityAlignment


# 定义一个简单的设备数据结构
@dataclass
class DeviceRecord:
    index: int
    name: str  # 块名
    name_str: str
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

        # 确保标注字体样式存在
        if 'LegendTextStyle' not in self.doc.styles:
            # doc.styles.new('DimStyle', dxfattribs={'font': '仿宋_GB2312.ttf'})
            self.doc.styles.new('LegendTextStyle', dxfattribs={
                'font': '宋体.ttf',
                # 'font': '仿宋_GB2312.ttf',
                'width': 0.75
            })

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
                name_str=block_name,
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

    # 1. 新增辅助方法：计算布局旋转角度
    def _get_layout_rotation(self, station_val):
        """
        根据桩号获取该点位所在布局视口的旋转角度。
        逻辑：复用之前的 RouteCalculator 逻辑，获取该桩号处的道路切线角度。
        为了在布局里看着是正的，模型空间里的文字需要旋转 -tangent_angle。
        """
        # 注意：这里需要 RouteCalculator 提供一个 get_direction_at(station) 方法
        # 如果 RouteCalculator 没有，我们需要简单实现一个
        # 简单起见，我们重新计算一下该桩号在 Route 上的切线

        # 使用 RouteCalculator 的内部数据寻找切线
        # 这是一个简化的查找，假设 route.segments 已经按桩号排序
        target_angle = 0.0
        for seg in self.route.segments:
            if seg['start_stat'] <= station_val <= (seg['start_stat'] + seg['logic_span']):
                # 找到了所在段，计算该段的向量角度
                vec = seg['vec']
                target_angle = vec.angle  # 弧度
                break

        # 布局视口通常旋转 -target_angle 变平
        # 所以为了让文字在布局里水平，文字在模型空间应该旋转 target_angle (或者 target_angle + pi)
        # 使得文字平行于道路
        return target_angle

    # 2. 新增核心方法：绘制图例和标注
    def draw_legends(self, devices, legend_source_file=None):
        """
        :param devices: extract_and_project_devices 返回的列表
        :param legend_source_file: 包含图例块的外部 DXF 文件路径。如果为 None，假设当前文件已有块。
        """
        print(f"正在绘制 {len(devices)} 个设备的图例注记...")

        needed_blocks = []
        for dev in devices:
            needed_blocks.append(f"{dev.name_str}_TL")

        # 如果提供了外部图例文件，需要先导入块定义
        if legend_source_file:
            self._import_blocks(legend_source_file, needed_blocks)

        # 标注图层
        layer_name = "DEVICE_LEGEND"
        if layer_name not in self.doc.layers:
            self.doc.layers.add(name=layer_name, color=7)  # 白色

        for dev in devices:
            # 1. 确定旋转角度
            # 我们希望文字和图例在布局里是正的。
            # 道路切线角度是 road_angle。
            # 布局旋转了 -road_angle。
            # 所以模型空间里的物体如果旋转 road_angle，在布局里就是水平的。
            road_angle_rad = self._get_layout_rotation(dev.station_val)
            rotation_deg = math.degrees(road_angle_rad)

            # 2. 计算引线避让位置
            # 策略：根据设备在左侧还是右侧，决定引线向外延伸的方向
            # 左侧设备向左引，右侧设备向右引
            # 初始引线长度 10m (根据实际单位调整，如果是mm则是10000)
            lead_dist = 15.0  # if self.route.segments[0]['len_sq'] < 10000 else 15000.0

            # 计算垂直于道路方向的向量 (法向量)
            # 道路向量 (cos, sin)
            # 左侧法向量 (-sin, cos), 右侧法向量 (sin, -cos)
            if dev.side == "左幅外侧" or dev.side == "Left":
                normal_vec = Vec2(-math.sin(road_angle_rad), math.cos(road_angle_rad))
            else:
                normal_vec = Vec2(math.sin(road_angle_rad), -math.cos(road_angle_rad))

            # 设备坐标
            p_dev = Vec2(dev.x, dev.y)

            # 图例插入点 (引线末端)
            p_legend = p_dev + normal_vec * lead_dist

            # 简单避让逻辑：如果和上一个太近，就再往外推或者沿道路方向错开
            # 这里暂时只做简单的垂直引出，复杂的力导向需要迭代计算

            # 3. 插入图例块
            legend_block_name = f"{dev.name_str}_TL"  # 约定后缀

            # 检查块是否存在，不存在则用默认块或跳过
            if legend_block_name not in self.doc.blocks:
                print(f"警告: 未找到图例块 {legend_block_name}，跳过图例绘制。")
                # 也可以画个圆圈代替
                self.msp.add_circle(p_legend, radius=2, dxfattribs={'layer': layer_name, 'color': 1})
            else:
                self.msp.add_blockref(
                    name=legend_block_name,
                    insert=p_legend,
                    dxfattribs={
                        'layer': layer_name,
                        'rotation': rotation_deg  # 跟随道路方向旋转
                    }
                )

            # 4. 绘制引线 (连接设备点和图例点)
            self.msp.add_line(p_dev, p_legend, dxfattribs={'layer': layer_name, 'color': 252})  # 灰色线

            # 5. 添加多行文字信息
            # 文字内容
            content = (
                f"名称: {dev.name}\n"
                f"桩号: {dev.station_str}\n"
                f"位置: {dev.side}\n"
                f"基础: 路基"
            )

            # 文字位置：在图例块旁边
            # 继续沿法向量向外偏移一点，或者沿道路方向偏移
            text_offset_dist = 5.0 if lead_dist < 100 else 5000.0
            p_text = p_legend + normal_vec * (text_offset_dist * 0.2)

            # 计算文字高度 (根据单位)
            text_h = 10 if lead_dist < 100 else 2000.0

            # 创建 MTEXT
            mtext = self.msp.add_mtext(
                content,
                dxfattribs={
                    'layer': layer_name,
                    'char_height': text_h,
                    'style': 'LegendTextStyle',
                    'rotation': rotation_deg,  # 旋转文字
                }
            )

            # 设置文字对齐和附着点
            # 这里的逻辑：左侧设备文字在左边右对齐，右侧设备文字在右边左对齐
            # 还需要考虑旋转后的相对位置，稍微复杂
            # 简化方案：统一放在图例上方或下方

            # 使用 set_location 设置对齐
            # attachment_point: 1=TopLeft, 2=TopCenter, 3=TopRight ...
            # 我们可以让文字始终相对于图例“竖直向上”排列（相对于旋转后的坐标系）

            # 计算文字框的偏移向量 (垂直于道路，平行于道路)
            # 这里直接设置位置即可，ezdxf 会处理旋转

            # 为了美观，我们把文字放在图例块的"上方" (相对于布局图纸的上方)
            # 布局的"上方"就是道路法线指向路外的反方向吗？不，是垂直于道路切线的方向。

            # 简单做法：文字放在图例引线末端旁边
            mtext.set_location(
                insert=p_legend + Vec2(0, text_h * 1.5).rotate(road_angle_rad),  # 稍微往"上"偏一点
                rotation=rotation_deg,
                attachment_point=7  # BottomLeft
            )

    def _import_blocks(self, source_dxf_path, needed_blocks):
        """从外部文件导入图例块"""
        try:
            source_doc = ezdxf.readfile(source_dxf_path)
            importer = Importer(source_doc, self.doc)
            # 导入所有块
            importer.import_blocks(needed_blocks)
            importer.finalize()
        except Exception as e:
            print(f"导入图块失败: {e}")