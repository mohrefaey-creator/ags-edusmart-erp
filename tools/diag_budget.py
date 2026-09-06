import json

path = "/home/frappe/frappe-bench/apps/erpnext/erpnext/accounts/doctype/budget/budget.json"
spec = json.load(open(path, encoding="utf-8"))
print("BUDGET_FIELDS")
for field in spec["fields"]:
    if field["fieldtype"] in ("Section Break", "Column Break"):
        continue
    print(
        "  ",
        field["fieldname"],
        field["fieldtype"],
        "reqd=" + str(field.get("reqd", 0)),
        "opts=" + str(field.get("options", ""))[:40],
    )

src = open(
    "/home/frappe/frappe-bench/apps/erpnext/erpnext/accounts/doctype/budget/budget.py",
    encoding="utf-8",
).read()
start = src.find("def validate_budget_amount")
print("VALIDATE_SNIPPET")
print(src[start:start + 900])
