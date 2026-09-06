// Desk-side helpers shared by AGS forms.
frappe.provide("ags");

ags.default_campus = function () {
	const boot = frappe.boot && frappe.boot.ags;
	return (boot && boot.default_campus) || null;
};

// Campus-bound users should only ever pick from their own campuses; this mirrors
// the server-side row scoping so the picker cannot offer an unusable value.
ags.campus_query = function () {
	const boot = frappe.boot && frappe.boot.ags;
	if (!boot || boot.unrestricted) return {};
	return { filters: { name: ["in", boot.campuses || []] } };
};

ags.apply_campus_defaults = function (frm, fieldname) {
	fieldname = fieldname || "campus";
	if (!frm.fields_dict[fieldname]) return;
	frm.set_query(fieldname, ags.campus_query);
	if (frm.is_new() && !frm.doc[fieldname]) {
		const campus = ags.default_campus();
		if (campus) frm.set_value(fieldname, campus);
	}
};

["AGS Fee Plan", "AGS Payer Account", "AGS Department Issue", "AGS Asset Handover",
 "AGS Collection Case", "AGS Quotation Comparison"].forEach(function (doctype) {
	frappe.ui.form.on(doctype, {
		onload: function (frm) { ags.apply_campus_defaults(frm); },
	});
});
