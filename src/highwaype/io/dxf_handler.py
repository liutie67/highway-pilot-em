# import math
# import ezdxf
# from ezdxf import path
# from ezdxf.math import Vec2
#
#
# class RouteCalculator:
#     """
#     辅助类：用于处理路径计算（桩号定位、切线方向）
#     """
#
#     def __init__(self, entity, step_precision=1.0):
#         # 1. 将 DXF 实体转换为 Path 对象 (保留圆弧精度)
#         self.path_obj = path.make_path(entity)
#
#         # 2. 将路径“扁平化”为一系列密集的点
#         # distance 参数控制精度，1.0 表示每隔 1 米或者在弯道处取样，保证几何近似度
#         # 这样可以将复杂的曲线计算转化为简单的线段插值
#         self.vertices = list(self.path_obj.flattening(distance=step_precision))
#
#         # 3. 预计算每个点的累计距离
#         self.dists = [0.0]
#         for i in range(1, len(self.vertices)):
#             p1 = self.vertices[i - 1]
#             p2 = self.vertices[i]
#             dist = p1.distance(p2)
#             self.dists.append(self.dists[-1] + dist)
#
#         self.total_length = self.dists[-1]
#
#     def get_info_at(self, target_dist):
#         """
#         根据距离返回：(坐标点 Vec2, 切线角度 radians)
#         """
#         if target_dist >= self.total_length:
#             # 如果超出终点，取最后两个点
#             p1, p2 = self.vertices[-2], self.vertices[-1]
#             return p2, (p2 - p1).angle
#
#         if target_dist <= 0:
#             p1, p2 = self.vertices[0], self.vertices[1]
#             return p1, (p2 - p1).angle
#
#         # 二分查找所在的线段 (或者简单的遍历，考虑到性能，线性遍历在出图时通常够用)
#         # 这里用简化的逻辑：找到第一个大于 target_dist 的点
#         idx = 0
#         for i, d in enumerate(self.dists):
#             if d > target_dist:
#                 idx = i
#                 break
#
#         # 目标在 idx-1 和 idx 之间
#         p_prev = self.vertices[idx - 1]
#         p_next = self.vertices[idx]
#         d_prev = self.dists[idx - 1]
#         d_next = self.dists[idx]
#
#         # 线性插值计算坐标
#         ratio = (target_dist - d_prev) / (d_next - d_prev)
#         location = p_prev.lerp(p_next, ratio)
#
#         # 计算切线角度 (atan2)
#         tangent_vec = p_next - p_prev
#         angle = tangent_vec.angle  # Vec2 的 angle 属性返回弧度
#
#         return location, angle
#
#
# class AutoPlotter:
#     def __init__(self, dxf_path, centerline_layer="CENTERLINE"):
#         self.doc = ezdxf.readfile(dxf_path)
#         self.msp = self.doc.modelspace()
#         self.centerline_layer = centerline_layer
#         self.paper_width = 420
#         self.paper_height = 297
#         self.scale = 1000
#         self.overlap = 0.1
#
#     def get_route(self):
#         """寻找并返回 RouteCalculator 对象"""
#         polylines = self.msp.query(f'LWPOLYLINE[layer=="{self.centerline_layer}"]')
#         if not polylines:
#             raise ValueError(f"未找到图层 {self.centerline_layer} 上的中心线")
#
#         longest_pl = max(polylines, key=lambda e: len(e))
#
#         # 返回自定义的计算器对象，而不是原生的 Polyline
#         return RouteCalculator(longest_pl, step_precision=0.5)
#
#     def calculate_frames(self, route):
#         frames = []
#         model_width = (self.paper_width * self.scale) / 1000.0
#         step_dist = model_width * (1 - self.overlap)
#
#         current_dist = 0.0
#         frame_idx = 1
#
#         # 使用 route.total_length
#         while current_dist < route.total_length:
#             # 调用我们自己写的 get_info_at
#             center_point, angle_rad = route.get_info_at(current_dist)
#
#             frames.append({
#                 'name': f"A3_Section_{frame_idx:03d}",
#                 'center': center_point,
#                 'rotation': angle_rad,
#                 'scale': self.scale
#             })
#
#             current_dist += step_dist
#             frame_idx += 1
#
#         return frames
#
#     def create_layouts(self, frames):
#         for frame in frames:
#             # 如果布局已存在，先删除（防止报错）
#             if frame['name'] in self.doc.layouts:
#                 self.doc.layouts.delete(frame['name'])
#
#             layout = self.doc.layouts.new(frame['name'])
#
#             # Viewport 参数
#             vp_width = self.paper_width
#             vp_height = self.paper_height
#             vp_center_paper = (vp_width / 2, vp_height / 2)
#
#             viewport = layout.add_viewport(
#                 center=vp_center_paper,
#                 size=(vp_width, vp_height),
#                 view_center_point=frame['center'],
#                 view_height=self.paper_height * self.scale / 1000.0
#             )
#
#             # 设置旋转
#             twist_angle = -frame['rotation']
#             viewport.dxf.view_twist_angle = math.degrees(twist_angle)
#             viewport.dxf.status = 1
#
#     def run(self, output_path):
#         try:
#             print("正在解析道路中心线...")
#             route = self.get_route()
#             print(f"道路全长: {route.total_length:.2f}米")
#
#             frames = self.calculate_frames(route)
#             print(f"计算出 {len(frames)} 个图幅...")
#
#             self.create_layouts(frames)
#             self.doc.saveas(output_path)
#             print(f"保存成功: {output_path}")
#         except Exception as e:
#             import traceback
#             traceback.print_exc()
#             print(f"错误: {e}")
#
#
# # 测试用例 (请确保目录下有 input.dxf 且有 CENTERLINE 图层)
# if __name__ == "__main__":
#     # plotter = AutoPlotter("test.dxf", centerline_layer="CENTERLINE")
#     # plotter.run("output_sliced.dxf")
#     pass

import math
import ezdxf
import ezdxf.path
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
    def __init__(self, dxf_path, centerline_layer="CENTERLINE"):
        print(f"1. 正在读取源文件: {dxf_path} ...")
        # 步骤 A: 只读读取源文件
        self.doc = ezdxf.readfile(dxf_path)
        self.msp = self.doc.modelspace()
        self.centerline_layer = centerline_layer

        # A3 设置
        self.paper_width = 420
        self.paper_height = 297
        self.scale = 1000
        self.overlap = 0.1

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

    def calculate_frames(self, route):
        frames = []
        model_width = (self.paper_width * self.scale) / 1000.0
        step_dist = model_width * (1 - self.overlap)
        current_dist = model_width / 2
        frame_idx = 1

        while current_dist < route.total_length:
            center_point, angle_rad = route.get_info_at(current_dist)
            frames.append({
                'name': f"A3_Sec_{frame_idx:03d}",
                'center': center_point,
                'rotation': angle_rad,
                'scale': self.scale
            })
            current_dist += step_dist
            frame_idx += 1
        return frames

    def create_layouts(self, frames):
        for frame in frames:
            if frame['name'] in self.doc.layouts: continue

            layout = self.doc.layouts.new(frame['name'])

            equal_margin = 5
            # 步骤 C: 设置页面显示范围 (解决打开是黑屏的问题)
            layout.page_setup(
                size=(self.paper_width, self.paper_height),
                margins=(equal_margin, equal_margin, equal_margin, equal_margin),  # 顺序：顺时针顺序
                units='mm',
                offset=(0, 0),  # 顺序：左下
                rotation=0
            )

            vp_center_paper = (self.paper_width / 2 - equal_margin, self.paper_height / 2 - equal_margin)  # 基于 margins, 左下的长度

            # 步骤 D: 使用正确的属性名 + 正确的数值类型
            # ezdxf 的属性通常接受“度数(Degrees)”，它内部会自动转弧度
            twist_degrees = -math.degrees(frame['rotation'])

            try:
                viewport = layout.add_viewport(
                    center=vp_center_paper,  # 视口框在“纸上”的位置
                    size=(self.paper_width-2*equal_margin, self.paper_height-2*equal_margin),  # 视口框在“纸上”的大小, 顺序：左下
                    view_center_point=frame['center'],  # 视口要看“模型空间”里的哪个坐标
                    view_height=(self.paper_height * self.scale) / 1000.0  # 核心：控制出图比例！
                )

                # ✅ 这里就是你文档里查到的正确属性！
                # 之前代码失效是因为 DXF 版本太低，而不是名字错了
                # viewport.dxf.view_twist_angle = twist_degrees

                # 开启并锁定
                viewport.dxf.status = 1  # 相当于“打开视口”。如果设为 0，视口内是空的，不显示模型空间内容。
                # viewport.dxf.flags = 90
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