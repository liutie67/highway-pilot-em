import math
import ezdxf
import ezdxf.path
from ezdxf import bbox
from ezdxf.math import Vec2
from ezdxf.addons import Importer


# ==========================================
# 1. 路由计算模块
# ==========================================
class RouteCalculator:
    def __init__(self, entity, step_precision=0.5):
        self.path_obj = ezdxf.path.make_path(entity)
        self.vertices = list(self.path_obj.flattening(distance=step_precision))
        self.dists = [0.0]
        for i in range(1, len(self.vertices)):
            dist = self.vertices[i - 1].distance(self.vertices[i])
            self.dists.append(self.dists[-1] + dist)
        self.total_length = self.dists[-1]

    def get_info_at(self, target_dist):
        if target_dist >= self.total_length:
            p1, p2 = self.vertices[-2], self.vertices[-1]
            return p2, (p2 - p1).angle
        if target_dist <= 0:
            p1, p2 = self.vertices[0], self.vertices[1]
            return p1, (p2 - p1).angle

        idx = 0
        for i, d in enumerate(self.dists):
            if d > target_dist:
                idx = i
                break

        p_prev = self.vertices[idx - 1]
        p_next = self.vertices[idx]
        d_prev = self.dists[idx - 1]
        d_next = self.dists[idx]

        ratio = (target_dist - d_prev) / (d_next - d_prev)
        location = p_prev.lerp(p_next, ratio)
        angle = (p_next - p_prev).angle
        return location, angle


# ==========================================
# 2. 自动绘图模块
# ==========================================
class AutoPlotter:
    def __init__(self, dxf_path, centerline_layer="CENTERLINE", standard_frame_margins=[10, 10, 20, 30], scale=1200):
        print(f"1. 正在读取源文件: {dxf_path} ...")
        # 步骤 A: 只读读取源文件
        self.doc = ezdxf.readfile(dxf_path)
        self.msp = self.doc.modelspace()
        self.centerline_layer = centerline_layer

        # A3 设置
        self.paper_width = 420
        self.paper_height = 297
        self.scale = scale
        self.overlap = 0.1
        self.standard_frame_margins = standard_frame_margins
        self.viewport_width = self.paper_width - self.standard_frame_margins[1] - self.standard_frame_margins[3]
        self.viewport_height = self.paper_height - self.standard_frame_margins[0] - self.standard_frame_margins[2]

    def import_frame_block(self, sd_frame_path):
        # 1. 读取图框源文件
        source_doc = ezdxf.readfile(sd_frame_path)

        # 2. 初始化导入器
        importer = Importer(source_doc, self.doc)

        # 3. 导入名为 "standard_frame" 的块
        # rename=False 表示不改名，如果重名则不导入（保留现有的）
        importer.import_blocks(["standard_frame"], rename=False)

        # 4. 提交更改
        importer.finalize()

    @staticmethod
    def _parse_station_to_m(pk_str):
        """
        辅助函数：将 'K1+450' 转换为数值 1450.0
        """
        try:
            # 去掉 'K'，处理可能的大小写
            clean_str = pk_str.upper().replace('K', '')
            if '+' in clean_str:
                parts = clean_str.split('+')
                km = int(parts[0])
                m = float(parts[1])
                return km * 1000 + m
            else:
                return float(clean_str)
        except Exception:
            return 0.0

    @staticmethod
    def _format_m_to_station(meters, precision=10):
        """
        辅助函数：将数值 1453.2 转换为 'K1+450'
        precision: 取整精度，默认10米
        """
        # 1. 按精度取整 (例如 1453 -> 1450)
        rounded_m = round(meters / precision) * precision

        # 2. 拆分公里和米
        km = int(rounded_m // 1000)
        m = int(rounded_m % 1000)

        # 3. 格式化字符串 (03d 保证米数显示为 010 而不是 10)
        return f"K{km}+{m:03d}"

    def get_route(self):
        # 从源文件中找线
        polylines = self.msp.query(f'LWPOLYLINE[layer=="{self.centerline_layer}"]')
        if not polylines:
            lines = self.msp.query(f'LINE[layer=="{self.centerline_layer}"]')
            if lines:
                return RouteCalculator(lines[0])
            raise ValueError(f"未找到图层 {self.centerline_layer} 上的中心线")
        longest_pl = max(polylines, key=lambda e: len(e))
        return RouteCalculator(longest_pl)

    def calculate_frames(self, route, start_PK = 'K0+000'):
        frames = []

        # 1. 计算图纸覆盖的模型空间宽度
        model_width = (self.viewport_width * self.scale) / 1000.0

        # 2. 计算步长 (考虑重叠率)
        step_dist = model_width * (1 - self.overlap)

        # 3. 解析起始桩号的基础数值 (例如 K0+000 -> 0.0, K2+500 -> 2500.0)
        base_offset_m = self._parse_station_to_m(start_PK)

        # 4. 初始化遍历
        # current_dist 是相对于 route 几何起点的距离
        current_dist = model_width / 2
        frame_idx = 1

        while current_dist < route.total_length:
            # 获取当前帧中心的坐标和角度
            # 注意：如果最后一段路很短，get_info_at 会自动处理边界
            center_point, angle_rad = route.get_info_at(current_dist)

            # 计算当前帧覆盖的 [相对] 起止距离 (相对于 Polyline 起点)
            # 这里的 max/min 是为了防止超出路线总长范围
            rel_start = max(0, current_dist - model_width / 2)
            rel_end = min(route.total_length, current_dist + model_width / 2)

            # 计算 [绝对] 桩号数值 (加上起始桩号偏移)
            abs_start_m = base_offset_m + rel_start
            abs_end_m = base_offset_m + rel_end

            frames.append({
                'name': f"平面图{frame_idx:03d}",
                'center': center_point,
                'rotation': angle_rad,
                'scale': self.scale,

                # --- 新增的属性 ---
                # 原始数值，方便后续如果有数学计算需要
                'start_station_val': abs_start_m,
                'end_station_val': abs_end_m,

                # 格式化后的标签 (例如 'K1+450')
                'start_station_label': self._format_m_to_station(abs_start_m, precision=10),
                'end_station_label': self._format_m_to_station(abs_end_m, precision=10),
            })

            # 移动到下一帧
            current_dist += step_dist
            frame_idx += 1

            # 边界检查：如果上一帧已经覆盖到了终点，就结束循环
            if rel_end >= route.total_length:
                break

        return frames

    def create_layouts(self, frames):
        len_frames = len(frames)
        for frame in frames:
            if frame['name'] in self.doc.layouts: continue

            layout = self.doc.layouts.new(frame['name'])

            equal_margin = 0
            # 步骤 C: 设置页面显示范围 (解决打开是黑屏的问题)
            layout.page_setup(
                size=(self.paper_width, self.paper_height),
                margins=(equal_margin, equal_margin, equal_margin, equal_margin),  # 顺序：顺时针顺序
                units='mm',
                offset=(0, 0),  # 顺序：左下
                rotation=0
            )

            # ---------------------------------------------------------
            # 1. 检查图块是否存在 (严格检查)
            # ---------------------------------------------------------
            if "standard_frame" not in self.doc.blocks:
                # 只是大声喊出“有错误！”，但不自杀
                raise ValueError("【严重错误】DXF中未找到 'standard_frame' 图块，无法继续！")

            # ---------------------------------------------------------
            # 2. 计算自动缩放比例 (Auto-Scaling)
            # ---------------------------------------------------------
            # 获取图块定义的句柄
            block_def = self.doc.blocks.get("standard_frame")

            # 计算该图块的边界框 (Bounding Box)
            # cache=None 表示不缓存，确保实时计算
            extents = bbox.extents(block_def, cache=None)

            # 获取原始宽度和高度
            orig_width = extents.size.x
            orig_height = extents.size.y

            # 安全检查：防止除以零（防止图块是空的）
            if orig_width <= 0 or orig_height <= 0:
                raise ValueError(f"【错误】图块 'standard_frame' 的尺寸异常 (宽:{orig_width}, 高:{orig_height})，无法计算缩放。")

            # 目标尺寸 (A3)
            target_width = 420.0
            target_height = 297.0

            # 计算 X 和 Y 方向所需的缩放因子
            # 逻辑：目标尺寸 / 原始尺寸 = 需要的缩放倍数
            scale_factor_x = target_width / orig_width
            scale_factor_y = target_height / orig_height

            # ---------------------------------------------------------
            # 3. 插入并应用缩放
            # ---------------------------------------------------------
            # 插入图块
            frame_blk = layout.add_blockref("standard_frame", (0, 0))

            # 应用计算出的比例
            frame_blk.dxf.xscale = scale_factor_x
            frame_blk.dxf.yscale = scale_factor_y

            # Z轴通常保持 1.0，或者是 X 和 Y 的较小值（如果是3D块）
            # 对于2D图框，保持 1.0 或等于 xscale 均可，这里保持 1.0 安全
            frame_blk.dxf.zscale = 1.0

            # (可选) 打印调试信息，方便你看它到底缩放了多少倍
            # print(f"图框原始尺寸: {orig_width:.2f}x{orig_height:.2f} -> 缩放倍数 X:{scale_factor_x:.4f}, Y:{scale_factor_y:.4f}")

            # 4. 准备属性数据 (字典)
            # Key: 必须是图块定义中 ATTDEF 的 "Tag" 名称 (大小写敏感，通常是大写)
            # Value: 你想填入的具体文字

            # 假设 frame 数据里有 start_station 和 end_station
            # 格式化桩号字符串，例如: "K0+000 - K0+500"
            st_str = f"{frame['start_station_label']} - {frame['end_station_label']}"

            # 自动获取当前 layout 的索引作为页码 (或者你自己维护一个计数器)
            page_num = str(frames.index(frame) + 1)

            values = {
                "桩号范围": st_str,  # 请核对你的图块属性 Tag 是否叫 RANGE
                "页码": page_num,  # 请核对你的图块属性 Tag 是否叫 PAGENO
                "总页码": len_frames  # 还可以填其他固定属性
            }

            # 5. 自动填充属性
            # 这个函数会自动查找块定义里的 ATTDEF，并创建对应的 ATTRIB 实体
            frame_blk.add_auto_attribs(values)

            # vp_center_paper = (self.paper_width / 2 - equal_margin - self.standard_frame_margins[2],
            #                    self.paper_height / 2 - equal_margin - self.standard_frame_margins[3])  # 基于 margins, 左下的长度
            vp_center_paper =(
                self.standard_frame_margins[3] + self.viewport_width/2,
                self.standard_frame_margins[2] + self.viewport_height/2
            )

            # 步骤 D: 使用正确的属性名 + 正确的数值类型
            # ezdxf 的属性通常接受“度数(Degrees)”，它内部会自动转弧度
            twist_degrees = -math.degrees(frame['rotation'])

            try:
                viewport = layout.add_viewport(
                    center=vp_center_paper,  # 视口框在“纸上”的位置
                    size=(self.paper_width-2*equal_margin - self.standard_frame_margins[1] - self.standard_frame_margins[3],
                          self.paper_height-2*equal_margin - self.standard_frame_margins[0] - self.standard_frame_margins[2]),  # 视口框在“纸上”的大小, 顺序：左下
                    # 【关键修改 A】: 告诉 ezdxf，视口的“偏移量”是 0
                    # 因为我们要让 target 直接对准中心，不需要再偏移了
                    view_center_point=(0, 0),
                    view_height=(self.paper_height * self.scale) / 1000.0  # 核心：控制出图比例！
                )

                # ✅ 这里就是你文档里查到的正确属性！
                # 之前代码失效是因为 DXF 版本太低，而不是名字错了
                # viewport.dxf.view_twist_angle = twist_degrees
                target_location = frame['center']  # 视口要看“模型空间”里的哪个坐标
                # 【关键修改 B】: 把旋转轴心 (Target) 搬到道路中心
                viewport.dxf.view_target_point = target_location
                viewport.dxf.view_twist_angle = twist_degrees

                # 同样把相机位置 (Direction) 搬过来
                # 这一步是为了保险，让相机看向 Target。如果不设，DXF 有时会默认从原点看过去。
                # 默认的 view_direction_vector 是 (0, 0, 1) (从顶往下看)，相对坐标，通常不用改。
                # 但 view_target_point 必须改！

                # 开启并锁定
                viewport.dxf.status = 1  # 相当于“打开视口”。如果设为 0，视口内是空的，不显示模型空间内容。
                # 定义锁定的常量
                VS_DISPLAY_LOCKED = 16384
                # 获取当前的 flags，然后加上锁定的 flag
                viewport.dxf.flags = viewport.dxf.flags | VS_DISPLAY_LOCKED

            except Exception as e:
                print(f"视口创建失败 {frame['name']}: {e}")

    def run(self, output_path):
        try:
            route = self.get_route()
            print(f"   道路全长: {route.total_length:.2f}m")

            # 步骤 E: 搬运底图 (Importer)
            # print("2. 正在搬运底图...")

            print("3. 计算分幅与生成布局...")
            frames = self.calculate_frames(route)
            self.create_layouts(frames)

            self.doc.saveas(output_path)
            print(f"✅ 保存成功: {output_path}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"❌ 错误: {e}")


if __name__ == "__main__":
    input_file = "dxf-original/会禄监控变更外场点位平面图-with_ROAD_CENTER.dxf"
    output_file = "final_output.dxf"

    import os

    if os.path.exists(input_file):
        plotter = AutoPlotter(input_file, centerline_layer="ROAD_CENTER")
        plotter.run(output_file)
    else:
        print("文件不存在")