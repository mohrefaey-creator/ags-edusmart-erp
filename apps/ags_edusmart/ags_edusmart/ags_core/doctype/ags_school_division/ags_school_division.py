import frappe
from frappe import _
from frappe.model.document import Document

from ags_edusmart.utils.grades import parse_grade_level


class AGSSchoolDivision(Document):
	def validate(self):
		self.validate_grade_range()

	def validate_grade_range(self):
		"""Programs carry no intrinsic order in Frappe Education, so the bounds
		are compared on the parsed year level rather than on the name."""
		if not (self.from_grade and self.to_grade):
			return
		low = parse_grade_level(self.from_grade)
		high = parse_grade_level(self.to_grade)
		if low is not None and high is not None and low > high:
			frappe.throw(
				_("From Grade ({0}) is above To Grade ({1}).").format(self.from_grade, self.to_grade)
			)
