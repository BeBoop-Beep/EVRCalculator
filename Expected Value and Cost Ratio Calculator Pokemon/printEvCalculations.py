from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill, NamedStyle
from openpyxl.utils.dataframe import dataframe_to_rows
import pandas as pd

def append_summary_to_existing_excel(file_path, summary_data, results):
    # Merge and prepare data
    combined_data = {**summary_data, **results}
    df = pd.DataFrame({
        "Metric": list(combined_data.keys()),
        "Value": list(combined_data.values())
    })

    # Load workbook
    wb = load_workbook(file_path)

    # Remove old Summary sheet if it exists
    if 'Summary' in wb.sheetnames:
        wb.remove(wb['Summary'])

    # Create new Summary sheet
    ws = wb.create_sheet(title='Summary')

    # Define border and font
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    header_font = Font(bold=True)
    currency_format = '"$"#,##0.00'
    percent_format = '0.00%'

    # Write headers
    ws.append(['Metric', 'Value'])
    for cell in ws[1]:
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border
        cell.fill = PatternFill(start_color="D9D9D9", fill_type="solid")

    # Write rows
    row_index = 2
    for metric, value in combined_data.items():
        ws.append([metric, value])
        row = ws[row_index]

        # Format EV and dollar-related values
        if 'ev' in metric.lower() or 'net_value' in metric.lower() or 'price' in metric.lower():
            row[1].number_format = currency_format

        # Format percentage values
        elif 'roi' in metric.lower() or 'hit_prob' in metric.lower():
            row[1].number_format = percent_format
            if 'roi' in metric.lower() and value > 1:
                row[1].value = value - 1  # Display as % gain over 100%

        # Borders & alignment
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='left')

        row_index += 1

    # Auto-size columns
    for col in ['A', 'B']:
        ws.column_dimensions[col].auto_size = True

    wb.save(file_path)
