import ezdxf
import sys
from typing import List, Optional, Union, Tuple
from pathlib import Path


class FrameAutoNumberer:
    """
    用于处理 DXF 图纸中的图框块（Frame Block），按空间顺序自动重写编号。
    属于 highway-pilot-pe 项目的一部分。

    该类会读取 DXF，识别包含 'TUNo' 属性的图框，根据“从上到下、从左到右”的规则排序，
    将 'TUNo' 属性的值修改为 1, 2, 3... 的序列，最后保存文件。

    Attributes
    ----------
    file_path : Path
        源 DXF 文件的路径。
    doc : ezdxf.document.Drawing
        加载后的 DXF 文档对象。
    """

    def __init__(self, file_path: Union[str, Path]):
        """
        初始化编号器并加载 DXF 文件。

        Parameters
        ----------
        file_path : str or Path
            源 DXF 文件路径。

        Raises
        ------
        FileNotFoundError
            如果源文件不存在。
        SystemExit
            如果文件损坏或不是 DXF 格式。
        """
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"未找到源文件: {self.file_path}")

        try:
            self.doc = ezdxf.readfile(self.file_path)
        except (IOError, ezdxf.DXFError) as e:
            print(f"读取 DXF 失败: {e}")
            sys.exit(1)

    def _get_sorted_frames(self, x_restrict: Optional[float], y_tolerance: float):
        """
        内部辅助方法：获取、过滤并排序所有图框实体。

        Parameters
        ----------
        x_restrict : float or None
            X 轴过滤阈值。
        y_tolerance : float
            Y 轴行判定容差。

        Returns
        -------
        list
            已排序的 ezdxf INSERT 实体列表。
        """
        msp = self.doc.modelspace()
        valid_frames = []

        # 1. 收集符合条件的图框
        for entity in msp.query('INSERT'):
            # --- 修复点 1: 使用更稳健的方式检查属性是否存在 ---
            # ezdxf 的 attribs 属性是一个列表，如果没有属性则为空列表
            # 直接判断列表长度即可，避免使用 has_attribs 标志位属性
            if len(entity.attribs) == 0:
                continue

            # 检查是否有 TUNo 属性 (大小写不敏感)
            has_tuno = False
            for attrib in entity.attribs:
                if attrib.dxf.tag.upper() == 'TUNO':
                    has_tuno = True
                    break

            if not has_tuno:
                continue

            # 坐标过滤
            insert_point = entity.dxf.insert
            if x_restrict is not None and insert_point.x <= x_restrict:
                continue

            valid_frames.append(entity)

        # 2. 排序逻辑
        # 先按 Y 轴降序排列 (从上到下)
        valid_frames.sort(key=lambda e: e.dxf.insert.y, reverse=True)

        sorted_frames = []
        if valid_frames:
            current_row = [valid_frames[0]]

            for frame in valid_frames[1:]:
                # 判断是否在同一行 (Y轴差异在容差内)
                last_y = current_row[0].dxf.insert.y
                curr_y = frame.dxf.insert.y

                if abs(last_y - curr_y) <= y_tolerance:
                    current_row.append(frame)
                else:
                    # 结算当前行：按 X 轴升序 (从左到右)
                    current_row.sort(key=lambda e: e.dxf.insert.x)
                    sorted_frames.extend(current_row)
                    current_row = [frame]

            # 结算最后一行
            if current_row:
                current_row.sort(key=lambda e: e.dxf.insert.x)
                sorted_frames.extend(current_row)

        return sorted_frames

    def renumber_and_save(self, output_path: Union[str, Path], x_restrict: Optional[float] = None,
                          y_tolerance: float = 1.0):
        """
        执行编号逻辑并保存文件。

        修改每个图框的 'TUNo' 属性，将其设置为从 1 开始的递增整数。
        仅当 x_restrict 限制右侧的图框会被修改，其余图框保持不变。

        Parameters
        ----------
        output_path : str or Path
            修改后的 DXF 文件保存路径。
        x_restrict : float, optional
            X 坐标起始限制。如果设置，只修改 X > x_restrict 的图框。默认为 None。
        y_tolerance : float, optional
            行对齐容差，用于模糊匹配 Y 坐标。默认为 1.0。

        Returns
        -------
        int
            成功修改并编号的图框数量。
        """
        # 获取排序后的实体对象
        sorted_entities = self._get_sorted_frames(x_restrict, y_tolerance)

        count = 0
        for idx, entity in enumerate(sorted_entities, start=1):

            # --- 修复点 2: 移除 get_attrib 调用，改为手动遍历 ---
            # 为了兼容不同版本的 ezdxf，直接遍历查找是最安全的方法
            target_attrib = None
            for attrib in entity.attribs:
                if attrib.dxf.tag.upper() == 'TUNO':
                    target_attrib = attrib
                    break

            # 修改属性值
            if target_attrib:
                target_attrib.dxf.text = str(idx)
                count += 1

        # 保存文件
        try:
            self.doc.saveas(output_path)
            print(f"成功处理 {count} 个图框，已保存至: {output_path}")
        except IOError as e:
            print(f"保存文件失败: {e}")

        return count


if __name__ == "__main__":
    # 测试用例
    input_file = "test_drawing.dxf"
    output_file = "test_drawing_numbered.dxf"

    # 模拟文件存在性检查
    if Path(input_file).exists():
        renumberer = FrameAutoNumberer(input_file)

        # 场景：只给 X 坐标大于 500 的图框重新编号，忽略左侧的图框
        # 容差设为 10.0 (假设图纸单位为 mm，且排版误差在 1cm 以内)
        processed_count = renumberer.renumber_and_save(
            output_path=output_file,
            x_restrict=500,
            y_tolerance=1.0
        )
    else:
        print(f"请准备测试文件: {input_file}")