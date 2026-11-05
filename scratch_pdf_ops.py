from pypdf import PdfReader

r = PdfReader(r"D:\MINI Project\Knowledge base\hod s of college.pdf")
p = r.pages[0]

def visitor_op(operator, operands, current_transformation_matrix):
    if operator == b'Do':
        print(f"Do {operands} at matrix y={current_transformation_matrix[5]}")
    elif operator == b'Tj' or operator == b'TJ':
        print(f"Text {operands} at matrix y={current_transformation_matrix[5]}")

print("Operations on Page 1:")
for op in p._extract_text(p, p.extract_text, visitor_op):
    pass

