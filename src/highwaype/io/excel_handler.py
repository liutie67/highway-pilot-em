import pandas as pd
import os


class ExcelManager:
    @staticmethod
    def save_device_list(devices, output_path, excel_infos):
        """
        将 DeviceRecord 对象列表保存为 Excel
        """
        if not devices:
            print("⚠️ 没有设备数据，跳过 Excel 导出。")
            return

        print(f"正在导出 Excel 到: {output_path} ...")

        base_type_names = {'Road': '路基', 'Bridge': '桥梁'}
        # 1. 转换为字典列表 (方便 Pandas 处理)
        data = []
        for d in devices:
            data.append({
                '序号': d.index,
                '设备名称': d.name,
                '桩号': d.station_str,
                '布设位置': d.side,
                '基础类型':base_type_names[d.base_type],
                '点位杆件':excel_infos[d.name][0],
                '点位配置': excel_infos[d.name][1],
                '备注': None,
                '偏距(m)': d.offset,
                'X坐标': d.x,
                'Y坐标': d.y,
                '数值桩号': d.station_val # 这一列通常作为隐藏列或不导出，看需求
            })

        # 2. 创建 DataFrame
        # df = pd.read_json(pd.io.json.dumps(data))  # 或者直接
        # df = pd.DataFrame(data)
        df = pd.DataFrame(data)

        # 3. 导出设置
        try:
            # 使用 xlsxwriter 引擎可以设置列宽等样式
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='点位一览表')

                # 获取 workbook 和 worksheet 对象进行格式调整
                workbook = writer.book
                worksheet = writer.sheets['点位一览表']

                # 定义样式
                header_fmt = workbook.add_format({
                    'bold': True,
                    'text_wrap': True,
                    'valign': 'top',
                    'fg_color': '#D7E4BC',  # 浅绿色表头
                    'border': 1
                })

                # 设置列宽
                worksheet.set_column('A:A', 5)  # 设备名称宽一点
                worksheet.set_column('B:B', 40)  # 设备名称宽一点
                worksheet.set_column('C:C', 10)  # 桩号宽一点
                worksheet.set_column('D:D', 10)
                worksheet.set_column('E:E', 10)
                worksheet.set_column('F:F', 25)
                worksheet.set_column('G:G', 40)

                # 应用表头样式 (Pandas 默认已经写了表头，这里其实是覆盖样式，稍微复杂)
                # 简单做法：只要数据存进去就行

            print(f"✅ Excel 导出成功！")

        except Exception as e:
            print(f"❌ Excel 导出失败 (请检查文件是否被打开): {e}")