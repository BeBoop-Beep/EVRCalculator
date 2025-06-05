def save_to_excel(cards, prices, excel_path):
    wb = load_workbook(excel_path)
    sheet = wb.active

    # Find or create columns
    headers = [cell.value for cell in sheet[1]]
    column_indices = {
        'Card Name': headers.index('Card Name') + 1 if 'Card Name' in headers else len(headers) + 1,
        'Price ($)': headers.index('Price ($)') + 1 if 'Price ($)' in headers else len(headers) + 2,
        'Reverse Variant Price ($)': headers.index('Reverse Variant Price ($)') + 1 if 'Reverse Variant Price ($)' in headers else len(headers) + 3,
        'Rarity': headers.index('Rarity') + 1 if 'Rarity' in headers else len(headers) + 4,
        'Pull Rate (1/X)': headers.index('Pull Rate (1/X)') + 1 if 'Pull Rate (1/X)' in headers else len(headers) + 5,
    }


    # Update headers if needed
    for col_name, col_idx in column_indices.items():
        if sheet.cell(row=1, column=col_idx).value != col_name:
            sheet.cell(row=1, column=col_idx, value=col_name)

    # Write data
    for i, card in enumerate(cards, 2):
        sheet.cell(row=i, column=column_indices['Card Name'], value=card['productName'])
        sheet.cell(row=i, column=column_indices['Price ($)'], value=card.get('Price ($)', ''))
        sheet.cell(row=i, column=column_indices['Reverse Variant Price ($)'], value=card.get('Reverse Variant Price ($)', ''))
        sheet.cell(row=i, column=column_indices['Rarity'], value=card.get('rarity', ''))
        sheet.cell(row=i, column=column_indices['Pull Rate (1/X)'], value=card.get('Pull Rate (1/X)', ''))

        # Align formatting
        for col_idx in column_indices.values():
            sheet.cell(row=i, column=col_idx).alignment = Alignment(horizontal='left', vertical='center')

    # Adjust column widths
    for col_letter in ['A', 'B', 'C', 'D', 'E']:
        max_length = max(len(str(cell.value)) if cell.value else 0 for cell in sheet[col_letter])
        sheet.column_dimensions[col_letter].width = max(15, max_length) * 1.2

    wb.save(excel_path)
    print(f"Successfully updated {len(cards)} cards.")