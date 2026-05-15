import json
import pandas as pd
import numpy as np
import os
import re
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


# 新增：数据比对相关的函数
def extract_json_from_log(log_file):
    """
    从日志文件中提取三种接口的JSON数据
    """
    if not os.path.exists(log_file):
        print(f"错误: 日志文件 {log_file} 不存在")
        return None

    interface_data = {
        "program": [],  # 收视接口
        "periodic": [],  # 周期接口
        "alarm": [],  # 告警接口
        "boot": []  # BOOT接口
    }

    print(f"开始解析日志文件: {log_file}")

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                json_start = -1
                json_data = None

                # 检查并提取三种接口的JSON数据
                if "program upload bean info" in line:
                    start_marker = "program upload bean info"
                    if "：" in line:
                        start_marker = "program upload bean info："

                    json_start = line.find(start_marker)
                    if json_start != -1:
                        json_start += len(start_marker)
                        json_str = line[json_start:].strip()

                        if json_str.startswith("{"):
                            try:
                                json_data = json.loads(json_str)
                                interface_data["program"].append(json_data)
                            except json.JSONDecodeError:
                                pass

                elif "periodic upload bean info" in line:
                    start_marker = "periodic upload bean info"
                    if "：" in line:
                        start_marker = "periodic upload bean info："
                    elif ":" in line:
                        start_marker = "periodic upload bean info:"

                    json_start = line.find(start_marker)
                    if json_start != -1:
                        json_start += len(start_marker)
                        json_str = line[json_start:].strip()

                        if json_str.startswith("{"):
                            try:
                                json_data = json.loads(json_str)
                                interface_data["periodic"].append(json_data)
                            except json.JSONDecodeError:
                                pass

                elif "alarm upload bean info" in line:
                    start_marker = "alarm upload bean info"
                    if"----" in line:
                        start_marker = "alarm upload bean info ----getDefaultRequestData---:"

                    json_start = line.find(start_marker)
                    if json_start != -1:
                        json_start += len(start_marker)
                        json_str = line[json_start:].strip()

                        if json_str.startswith("{"):
                            try:
                                json_data = json.loads(json_str)
                                interface_data["alarm"].append(json_data)
                            except json.JSONDecodeError:
                                pass

                elif "boot upload bean info" in line:
                    start_marker = "boot upload bean info"
                    if "：" in line:
                        start_marker = "boot upload bean info："
                    elif ":" in line:
                        start_marker = "boot upload bean info:"

                    json_start = line.find(start_marker)
                    if json_start != -1:
                        json_start += len(start_marker)
                        json_str = line[json_start:].strip()

                        if json_str.startswith("{"):
                            try:
                                json_data = json.loads(json_str)
                                interface_data["boot"].append(json_data)
                            except json.JSONDecodeError:
                                pass

        print("日志解析完成:")
        print(f"  收视接口数据条数: {len(interface_data['program'])}")
        print(f"  周期接口数据条数: {len(interface_data['periodic'])}")
        print(f"  告警接口数据条数: {len(interface_data['alarm'])}")
        print(f"  BOOT接口数据条数: {len(interface_data['boot'])}")

        return interface_data

    except Exception as e:
        print(f"解析日志文件时出错: {e}")
        return None


def find_field_in_json(json_data, field_path):
    """
    根据字段路径在JSON中查找对应值，支持列表索引和忽略字段前后的空格
    """
    if not field_path:
        return None

    try:
        parts = field_path.split('.')
        current = json_data

        for part in parts:
            part = part.strip()
            if not part:
                continue

            if '[' in part and ']' in part:
                match = re.match(r'([^[]+)\[(\d+)\]', part)
                if match:
                    field_name = match.group(1).strip()
                    index = int(match.group(2).strip())

                    found_key = None
                    for key in current.keys() if isinstance(current, dict) else []:
                        if key.strip() == field_name:
                            found_key = key
                            break

                    if found_key and isinstance(current[found_key], list) and 0 <= index < len(current[found_key]):
                        current = current[found_key][index]
                    else:
                        return None
                else:
                    return None
            else:
                found = False
                for key in current.keys() if isinstance(current, dict) else []:
                    if key.strip() == part:
                        current = current[key]
                        found = True
                        break

                if not found:
                    for key in current.keys() if isinstance(current, dict) else []:
                        key_normalized = key.strip().lower().replace('_', '').replace('-', '')
                        part_normalized = part.lower().replace('_', '').replace('-', '')
                        if key_normalized == part_normalized:
                            current = current[key]
                            found = True
                            break

                    if not found:
                        return None

        return current
    except Exception as e:
        return None


def get_field_name_without_index(field_name):
    """
    从字段名中移除索引部分
    例如：appLiveList[0] -> appLiveList
    """
    if not field_name:
        return field_name

    if '[' in field_name and ']' in field_name:
        match = re.match(r'([^[]+)\[(\d+)\]', field_name)
        if match:
            return match.group(1).strip()

    return field_name.strip()


def is_list_field(field_name, json_data, current_path=""):
    """
    判断一个字段是否是列表字段
    """
    if not field_name:
        return False

    clean_field_name = get_field_name_without_index(field_name)

    try:
        if current_path:
            full_path = f"{current_path}.{clean_field_name}" if current_path else clean_field_name
        else:
            full_path = clean_field_name

        value = find_field_in_json(json_data, full_path)

        if isinstance(value, list):
            return True
        elif isinstance(value, dict):
            return False
    except:
        pass

    return False


def build_field_path_with_hierarchy(df, idx, json_data):
    """
    根据Excel的层级结构构建字段路径，支持列表索引和忽略字段前后的空格
    """
    row = df.iloc[idx]

    param1 = str(row.get('参数1', '')).strip() if pd.notna(row.get('参数1')) else ''
    param2 = str(row.get('参数2', '')).strip() if pd.notna(row.get('参数2')) else ''
    param3 = str(row.get('参数3', '')).strip() if pd.notna(row.get('参数3')) else ''

    if param1 == 'nan' or param1 == '---' or param1 == '':
        param1 = ''
    if param2 == 'nan' or param2 == '---' or param2 == '':
        param2 = ''
    if param3 == 'nan' or param3 == '---' or param3 == '':
        param3 = ''

    def check_and_add_index(field_name, parent_path=""):
        if not field_name:
            return field_name

        if '[' in field_name and ']' in field_name:
            return field_name

        if is_list_field(field_name, json_data, parent_path):
            return f"{field_name}[0]"

        return field_name

    if param1 and param2 and param3:
        param1_with_index = check_and_add_index(param1)
        return f"{param1_with_index}.{param2}.{param3}"

    elif param1 and param2 and not param3:
        param1_with_index = check_and_add_index(param1)
        param2_with_index = check_and_add_index(param2, param1_with_index)
        return f"{param1_with_index}.{param2_with_index}"

    elif param1 and not param2 and not param3:
        return check_and_add_index(param1)

    elif not param1 and param2 and not param3:
        parent_param1 = None
        parent_idx = None

        for i in range(idx - 1, -1, -1):
            prev_row = df.iloc[i]
            prev_param1 = str(prev_row.get('参数1', '')).strip() if pd.notna(prev_row.get('参数1')) else ''
            prev_param1 = prev_param1.strip()
            if prev_param1 and prev_param1 != 'nan' and prev_param1 != '---' and prev_param1 != '':
                parent_param1 = prev_param1
                parent_idx = i
                break

        if parent_param1:
            parent_param1_with_index = check_and_add_index(parent_param1)
            param2_with_index = check_and_add_index(param2, parent_param1_with_index)
            return f"{parent_param1_with_index}.{param2_with_index}"
        else:
            return check_and_add_index(param2)

    elif not param1 and param2 and param3:
        parent_param1 = None
        for i in range(idx - 1, -1, -1):
            prev_row = df.iloc[i]
            prev_param1 = str(prev_row.get('参数1', '')).strip() if pd.notna(prev_row.get('参数1')) else ''
            prev_param1 = prev_param1.strip()
            if prev_param1 and prev_param1 != 'nan' and prev_param1 != '---' and prev_param1 != '':
                parent_param1 = prev_param1
                break

        if parent_param1:
            parent_param1_with_index = check_and_add_index(parent_param1)
            param2_with_index = check_and_add_index(param2, parent_param1_with_index)
            return f"{parent_param1_with_index}.{param2_with_index}.{param3}"
        else:
            param2_with_index = check_and_add_index(param2)
            return f"{param2_with_index}.{param3}"

    elif not param1 and not param2 and param3:
        parent_param2 = None
        parent_param2_idx = None

        for i in range(idx - 1, -1, -1):
            prev_row = df.iloc[i]
            prev_param2 = str(prev_row.get('参数2', '')).strip() if pd.notna(prev_row.get('参数2')) else ''
            prev_param2 = prev_param2.strip()
            if prev_param2 and prev_param2 != 'nan' and prev_param2 != '---' and prev_param2 != '':
                parent_param2 = prev_param2
                parent_param2_idx = i
                break

        if parent_param2:
            grandparent_param1 = None
            if parent_param2_idx is not None:
                for i in range(parent_param2_idx, -1, -1):
                    prev_row = df.iloc[i]
                    prev_param1 = str(prev_row.get('参数1', '')).strip() if pd.notna(prev_row.get('参数1')) else ''
                    prev_param1 = prev_param1.strip()
                    if prev_param1 and prev_param1 != 'nan' and prev_param1 != '---' and prev_param1 != '':
                        grandparent_param1 = prev_param1
                        break

            if grandparent_param1:
                grandparent_param1_with_index = check_and_add_index(grandparent_param1)
                parent_param2_clean = get_field_name_without_index(parent_param2)
                parent_param2_with_index = check_and_add_index(parent_param2_clean, grandparent_param1_with_index)
                return f"{grandparent_param1_with_index}.{parent_param2_with_index}.{param3}"
            else:
                parent_param2_clean = get_field_name_without_index(parent_param2)
                parent_param2_with_index = check_and_add_index(parent_param2_clean)
                return f"{parent_param2_with_index}.{param3}"
        else:
            parent_param1 = None
            for i in range(idx - 1, -1, -1):
                prev_row = df.iloc[i]
                prev_param1 = str(prev_row.get('参数1', '')).strip() if pd.notna(prev_row.get('参数1')) else ''
                prev_param1 = prev_param1.strip()
                if prev_param1 and prev_param1 != 'nan' and prev_param1 != '---' and prev_param1 != '':
                    parent_param1 = prev_param1
                    break

            if parent_param1:
                parent_param1_with_index = check_and_add_index(parent_param1)
                return f"{parent_param1_with_index}.{param3}"
            else:
                return param3

    else:
        return None


def perform_interface_comparison(log_file_path, base_excel_path="软探针接口字段.xlsx"):
    """
    执行接口数据比对
    """
    try:
        # 从日志中提取JSON数据
        interface_data = extract_json_from_log(log_file_path)
        if not interface_data:
            return False, "无法从日志中提取数据"

        # 检查基础Excel文件是否存在
        if not os.path.exists(base_excel_path):
            return False, f"基础Excel文件不存在: {base_excel_path}"

        # 加载Excel文件
        df = pd.read_excel(base_excel_path, sheet_name=0, header=0)

        # 使用openpyxl直接操作Excel
        wb = load_workbook(base_excel_path)
        ws = wb.active

        # 找到最后一列
        last_col = ws.max_column

        # 计算需要添加的列数（所有接口中数据条数的最大值）
        max_data_count = max(
            len(interface_data.get("program", [])),
            len(interface_data.get("periodic", [])),
            len(interface_data.get("alarm", [])),
            len(interface_data.get("boot", []))
        )

        if max_data_count == 0:
            return False, "所有接口都没有数据"

        # 创建列标题
        col_titles = ["上报内容"]
        for i in range(1, max_data_count):
            col_titles.append(f"上报内容-{i}")

        # 添加列到Excel
        col_indices = []
        current_col = last_col + 1

        for i, title in enumerate(col_titles):
            ws.cell(row=1, column=current_col + i, value=title)
            col_indices.append(current_col + i)

        total_processed = 0

        # 处理每个接口
        interface_configs = [
            {
                "name": "周期接口",
                "type": "periodic",
                "start_marker": "周期接口",
                "next_markers": ["收视接口", "告警接口", "BOOT接口", "---"]
            },
            {
                "name": "收视接口",
                "type": "program",
                "start_marker": "收视接口",
                "next_markers": ["周期接口", "告警接口", "BOOT接口", "---"]
            },
            {
                "name": "告警接口",
                "type": "alarm",
                "start_marker": "告警接口",
                "next_markers": ["周期接口", "收视接口", "BOOT接口", "---"]
            },
            {
                "name": "BOOT接口",
                "type": "boot",
                "start_marker": "BOOT接口",
                "next_markers": ["周期接口", "收视接口", "告警接口", "---"]
            }
        ]

        for config in interface_configs:
            interface_type = config["type"]
            interface_name = config["name"]

            # 确保interface_type是字符串类型
            if not isinstance(interface_type, str):
                continue
                
            data_list = interface_data.get(interface_type, [])
            data_count = len(data_list)

            if data_count == 0:
                continue

            # 找到接口开始位置
            interface_start = None
            for idx, row in df.iterrows():
                excel_interface_name = str(row.get('接口名称', '')).strip() if pd.notna(row.get('接口名称')) else ''
                excel_interface_name = excel_interface_name.strip()
                if excel_interface_name == config["start_marker"]:
                    interface_start = idx
                    break

            if interface_start is None:
                continue

            # 找到接口结束位置
            interface_end = None
            for idx in range(interface_start + 1, len(df)):
                excel_interface_name = str(df.iloc[idx].get('接口名称', '')).strip() if pd.notna(
                    df.iloc[idx].get('接口名称')) else ''
                excel_interface_name = excel_interface_name.strip()
                if excel_interface_name in config["next_markers"]:
                    interface_end = idx - 1
                    break

            if interface_end is None:
                interface_end = len(df) - 1

            if interface_end < interface_start:
                interface_end = interface_start

            # 处理该接口的每一行
            processed_count = 0
            for idx in range(interface_start, interface_end + 1):
                if idx == interface_start:
                    continue

                row = df.iloc[idx]

                param1 = str(row.get('参数1', '')).strip() if pd.notna(row.get('参数1')) else ''
                param2 = str(row.get('参数2', '')).strip() if pd.notna(row.get('参数2')) else ''
                param3 = str(row.get('参数3', '')).strip() if pd.notna(row.get('参数3')) else ''

                param1 = param1.strip()
                param2 = param2.strip()
                param3 = param3.strip()

                if not param1 and not param2 and not param3:
                    continue

                # 构建字段路径（使用第一个JSON数据来构建路径）
                if data_list:
                    field_path = build_field_path_with_hierarchy(df, idx, data_list[0])
                    if not field_path:
                        if param3:
                            field_path = param3
                        else:
                            continue

                # 遍历该接口的所有数据
                for data_idx in range(min(data_count, max_data_count)):
                    json_data = data_list[data_idx]
                    col_idx = col_indices[data_idx]

                    field_value = find_field_in_json(json_data, field_path)

                    if field_value is None:
                        report_content = "指标未上报"
                    elif field_value == "" or (isinstance(field_value, (list, dict)) and not field_value):
                        report_content = "有字段上报但为空"
                    elif isinstance(field_value, (int, float)) and field_value == 0:
                        report_content = "有字段上报为0"
                    elif isinstance(field_value, str) and field_value == '0':
                        report_content = "有字段上报为0"
                    else:
                        if isinstance(field_value, (dict, list)):
                            report_content = json.dumps(field_value, ensure_ascii=False)
                        else:
                            report_content = str(field_value)

                    ws.cell(row=idx + 2, column=col_idx, value=report_content)

                    if data_idx == 0:
                        processed_count += 1
                        total_processed += 1

            print(f"  {interface_name}处理完成: {processed_count} 个字段")

        # 保存结果文件
        result_file = "软探针接口上报指标整理_结果.xlsx"
        wb.save(result_file)

        # 返回成功和结果文件路径
        return True, result_file

    except Exception as e:
        return False, f"比对过程中出错: {str(e)}"