"""Arabic translations for sentences: validation messages, dialog titles,
portal copy and the AI layer's narration fragments.

Split from ``ar_translations.py`` (which holds terminology) because these need a
different kind of review: a term is right or wrong, a sentence also has to read
naturally.

Placeholders ({0}, {1}) are positional and must survive intact. Arabic word
order differs from English, so they are placed where the Arabic sentence needs
them rather than where English happened to put them.
"""

MESSAGES = {
	# ------------------------------------------------------- dialog titles
	"Approval Pending": "بانتظار الاعتماد",
	"Approval Rejected": "تم رفض الاعتماد",
	"Assets Not Returned": "لم تُرجع العهد",
	"Budget Exceeded": "تجاوز الميزانية",
	"Budget Warning": "تنبيه الميزانية",
	"Cannot Apply Discount": "تعذر تطبيق الخصم",
	"Company Mismatch": "عدم تطابق الشركة",
	"Currency Mismatch": "عدم تطابق العملة",
	"Empty Scope": "نطاق فارغ",
	"Insufficient Stock": "المخزون غير كافٍ",
	"Invalid Identifier": "معرّف غير صالح",
	"Justification Required": "المبرر مطلوب",
	"Override Approval Required": "يلزم اعتماد التجاوز",
	"Payer Mismatch": "عدم تطابق الدافع",
	"Three-Way Match Failed": "فشل المطابقة الثلاثية",

	# ---------------------------------------------------------- validation
	"A rejection reason is required.": "سبب الرفض مطلوب.",
	"Add at least one asset.": "أضف أصلاً واحداً على الأقل.",
	"Add at least one fee component.": "أضف بند رسوم واحداً على الأقل.",
	"Add at least one item.": "أضف صنفاً واحداً على الأقل.",
	"Ask a question.": "اطرح سؤالاً.",
	"Asset {0} is listed twice.": "الأصل {0} مُدرج مرتين.",
	"Cancel credit note {0} first.": "ألغِ الإشعار الدائن {0} أولاً.",
	"Cancel the linked invoice(s) first: {0}": "ألغِ الفواتير المرتبطة أولاً: {0}",
	"Customer {0} does not exist.": "العميل {0} غير موجود.",
	"Fee plan {0} is cancelled.": "خطة الرسوم {0} ملغاة.",
	"Fee plan {0} is not submitted.": "خطة الرسوم {0} غير معتمدة.",
	"Fee plan {0} created as draft.": "تم إنشاء خطة الرسوم {0} كمسودة.",
	"From and to employee are the same.": "الموظف المرسل والمستلم متطابقان.",
	"Handover {0} is not submitted.": "تسليم العهدة {0} غير معتمد.",
	"Installment {0} has no billable lines.":
		"القسط {0} لا يحتوي على بنود قابلة للفوترة.",
	"Installment {0} not found on {1}.": "القسط {0} غير موجود في {1}.",
	"Invoice {0} belongs to {1}, not {2}.": "الفاتورة {0} تخص {1} وليس {2}.",
	"Invoice {0} is not submitted.": "الفاتورة {0} غير معتمدة.",
	"Invoice {0} not found.": "الفاتورة {0} غير موجودة.",
	"Invoiced {0} but only {1} received.": "تمت فوترة {0} بينما استُلم {1} فقط.",
	"No goods receipt exists for {0}.": "لا يوجد استلام بضاعة للصنف {0}.",
	"No pending level found on this request.": "لا يوجد مستوى معلّق في هذا الطلب.",
	"Nothing to waive on invoice {0}.": "لا يوجد مبلغ للإعفاء في الفاتورة {0}.",
	"Only {0} can acknowledge this handover.":
		"{0} فقط يمكنه الإقرار باستلام هذه العهدة.",
	"Only {0} may act on level {1}.": "{0} فقط يمكنه اتخاذ إجراء على المستوى {1}.",
	"Order {0} belongs to {1}.": "أمر الشراء {0} يخص {1}.",
	"Payer account {0} has no customer.": "حساب الدافع {0} غير مرتبط بعميل.",
	"Please sign in.": "الرجاء تسجيل الدخول.",
	"Scholarship {0} is not active.": "المنحة {0} غير نشطة.",
	"Select the awarded supplier first.": "اختر المورد المرسى عليه أولاً.",
	"Student {0} is listed twice.": "الطالب {0} مُدرج مرتين.",
	"Submit the fee plan before invoicing.": "اعتمد خطة الرسوم قبل إصدار الفواتير.",
	"This request is already {0}.": "هذا الطلب {0} بالفعل.",
	"Unknown analysis: {0}": "تحليل غير معروف: {0}",
	"Waiver amount must be greater than zero.":
		"يجب أن يكون مبلغ الإعفاء أكبر من صفر.",
	"Not permitted.": "غير مصرح.",
	"Not permitted for this campus.": "غير مصرح لهذا الحرم المدرسي.",
	"Not permitted for this student.": "غير مصرح لهذا الطالب.",
	"You do not have access to campus {0}.":
		"ليس لديك صلاحية الوصول إلى الحرم المدرسي {0}.",
	"{0} cannot be before the joining date.":
		"لا يمكن أن يكون {0} قبل تاريخ الالتحاق.",
	"{0} {1} is still awaiting approval.": "{0} {1} ما زال بانتظار الاعتماد.",
	"{0} {1} was rejected in approval.": "{0} {1} تم رفضه في الاعتماد.",

	# ------------------------------------------------- descriptions / hints
	"Blank applies to every campus.":
		"الفراغ يعني التطبيق على جميع الأحرام المدرسية.",
	"Ignored when the trigger is On Due Date.":
		"يُتجاهل عندما يكون المُشغّل في تاريخ الاستحقاق.",
	"Leave blank for the provider default.":
		"اتركه فارغاً لاستخدام الإعداد الافتراضي للمزوّد.",
	"Lower wins when several matrices match.":
		"الأقل له الأولوية عند تطابق أكثر من مصفوفة.",
	"Optional Python expression over `doc`.":
		"تعبير Python اختياري يُطبّق على `doc`.",
	"Pre-selected on new documents.": "محدد مسبقاً في المستندات الجديدة.",
	"Zero means no upper bound.": "الصفر يعني عدم وجود حد أعلى.",
	"e.g. Grade 9 Laboratory.": "مثال: مختبر الصف التاسع.",

	# --------------------------------------------------- installment labels
	"Full Year": "السنة كاملة",
	"Term {0}": "الفصل {0}",
	"Quarter {0}": "الربع {0}",
	"Month {0}": "الشهر {0}",
	"Installment {0} of {1}": "القسط {0} من {1}",

	# -------------------------------------------------------- notifications
	"Acknowledged by {0}.": "تم الإقرار بواسطة {0}.",
	"AGS Department Issue {0} - {1}": "صرف مواد لقسم {0} - {1}",
	"Asset return overdue: {0}": "تأخر إرجاع العهدة: {0}",
	"{0} was due to return assets on {1}.": "كان على {0} إرجاع العهد بتاريخ {1}.",
	"Maintenance {0}: {1}": "الصيانة {0}: {1}",
	"Task '{0}' on {1} is due {2}.": "المهمة '{0}' على {1} مستحقة بتاريخ {2}.",
	"{0} {1} for {2}": "{0} {1} لـ {2}",
	"{0} for {1} expires on {2}.": "{0} الخاص بـ {1} ينتهي بتاريخ {2}.",
	"has expired": "منتهي الصلاحية",
	"expires soon": "يوشك على الانتهاء",
	"due": "مستحقة",
	"overdue": "متأخرة",
	"Iqama expiry": "انتهاء الإقامة",
	"Passport expiry": "انتهاء جواز السفر",
	"Professional license expiry": "انتهاء الرخصة المهنية",

	# --------------------------------------------------------------- portal
	"My Children": "أبنائي",
	"My Requests": "طلباتي",
	"My Workspace": "مساحة عملي",
	"Pay School Fees": "سداد الرسوم الدراسية",
	"Fees & Payments": "الرسوم والمدفوعات",
	"Fees & Collections": "الرسوم والتحصيل",
	"Request Leave": "طلب إجازة",
	"Iqama expires": "تنتهي الإقامة",
	"No assets are currently issued to you.": "لا توجد عهد مسلّمة لك حالياً.",
	"No installments scheduled.": "لا توجد أقساط مجدولة.",
	"No invoices yet.": "لا توجد فواتير بعد.",
	"No leave allocated.": "لا يوجد رصيد إجازات مخصص.",
	"You have not raised any requests.": "لم تقم بتقديم أي طلبات.",
	"No children are linked to your account yet.":
		"لا يوجد أبناء مرتبطون بحسابك بعد.",

	# ------------------------------------------------------ AI: titles
	"Outstanding school fees": "الرسوم الدراسية المتبقية",
	"Overdue by campus": "المتأخرات حسب الحرم المدرسي",
	"Operating margin drivers": "محركات هامش التشغيل",
	"Budget overruns": "تجاوزات الميزانية",
	"Expected collection": "التحصيل المتوقع",
	"Revenue trend": "اتجاه الإيرادات",
	"Collection performance": "أداء التحصيل",
	"Supplier performance": "أداء الموردين",
	"Delayed purchase orders": "أوامر الشراء المتأخرة",
	"Items purchased above their historical price":
		"أصناف اشتُريت بأعلى من سعرها التاريخي",
	"Consolidation opportunities": "فرص دمج المشتريات",
	"Items forecast to run out": "أصناف يُتوقع نفادها",
	"Department consumption outliers": "أقسام ذات استهلاك غير معتاد",
	"Non-moving stock": "المخزون الراكد",
	"Absenteeism by department": "الغياب حسب القسم",
	"Projected annual payroll": "الرواتب السنوية المتوقعة",
	"Documents expiring within {0} days": "مستندات تنتهي خلال {0} يوماً",
	"Payers more than {0} days overdue": "دافعون متأخرون أكثر من {0} يوماً",
	"Students at attendance risk": "طلاب معرضون لخطر الغياب",
	"Classes with declining results": "فصول ذات نتائج متراجعة",
	"Class averages below the school mean": "فصول دون متوسط المدرسة",

	# --------------------------------------------- AI: narration fragments
	"Main drivers:": "المحركات الرئيسية:",
	"Basis: {0}": "الأساس: {0}",
	"all campuses": "جميع الأحرام المدرسية",
	"There is not enough data to answer this confidently yet.":
		"لا تتوفر بيانات كافية للإجابة على هذا بثقة حتى الآن.",
	"up {0}%": "ارتفاع {0}%",
	"down {0}%": "انخفاض {0}%",
	"flat": "دون تغيير",
	"fell": "انخفض",
	"rose": "ارتفع",
	"held": "استقر",
	"has no prior-year comparison": "لا توجد مقارنة بالعام السابق",
	"This period": "هذه الفترة",
	"Same period last year": "نفس الفترة من العام الماضي",
	"Falling due in window": "المستحق خلال الفترة",
	"Observed collection rate": "معدل التحصيل الملاحظ",
	"Expected from scheduled": "المتوقع من المجدول",
	"Overdue book": "رصيد المتأخرات",
	"Expected recovery": "التحصيل المتوقع من المتأخرات",
	"Of which overdue": "منها متأخر",
	"Overdue share": "نسبة المتأخر",
	"Margin %": "نسبة الهامش",

	# --------------------------------------------- AI: "nothing found" answers
	"Nothing is currently outstanding.": "لا يوجد رصيد متبقٍ حالياً.",
	"No account is over budget.": "لا يوجد حساب تجاوز ميزانيته.",
	"No budgets are set for {0}.": "لا توجد ميزانيات محددة لـ {0}.",
	"No fee invoices have been raised yet.": "لم تُصدر أي فواتير رسوم بعد.",
	"No revenue is posted in either period.":
		"لا توجد إيرادات مسجلة في أي من الفترتين.",
	"No payer is more than {0} days overdue.":
		"لا يوجد دافع متأخر أكثر من {0} يوماً.",
	"No student is below {0}% attendance.":
		"لا يوجد طالب دون نسبة حضور {0}%.",
	"No campus currently carries an overdue balance.":
		"لا يوجد حرم مدرسي لديه رصيد متأخر حالياً.",
	"No purchase order is past its required date.":
		"لا يوجد أمر شراء تجاوز تاريخه المطلوب.",
	"No employee document expires in the next {0} days.":
		"لا يوجد مستند موظف ينتهي خلال {0} يوماً القادمة.",
	"No item's latest price is more than {0}% above its own average.":
		"لا يوجد صنف تجاوز سعره الأخير متوسطه بأكثر من {0}%.",
	"No class average has fallen between the two periods.":
		"لم ينخفض متوسط أي فصل بين الفترتين.",
	"Every item in stock has moved in the last {0} months.":
		"جميع أصناف المخزون تحركت خلال {0} أشهر الماضية.",
	"Nothing is scheduled or outstanding in this window.":
		"لا يوجد مجدول أو متبقٍ في هذه الفترة.",
	"No department stands out: consumption is evenly spread across {0} departments.":
		"لا يوجد قسم شاذ: الاستهلاك موزع بالتساوي على {0} قسماً.",
	"No item is forecast to run out within {0} days at current usage.":
		"لا يوجد صنف يُتوقع نفاده خلال {0} يوماً بمعدل الاستهلاك الحالي.",
	"No item was requested more than once in the last {0} days.":
		"لم يُطلب أي صنف أكثر من مرة خلال {0} يوماً الماضية.",
	"No purchase orders were placed in this period.":
		"لم تُصدر أوامر شراء في هذه الفترة.",
	"No class sits more than {0} points below the school average of {1}%.":
		"لا يوجد فصل يقل عن متوسط المدرسة ({1}%) بأكثر من {0} نقطة.",
	"There is no posted revenue in either period to compare.":
		"لا توجد إيرادات مسجلة في أي من الفترتين للمقارنة.",
}
