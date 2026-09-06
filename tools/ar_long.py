"""Arabic translations for field descriptions and long-form sentences.

Third and last mapping module (terminology in ``ar_translations``, short
messages in ``ar_messages``). These are the help texts under form fields and the
full sentences the AI layer produces.

Two conventions here:

* Handover cross-references ("SKILL sec. 17.6") are kept verbatim. They point at
  an English document; translating the pointer would break the trail.
* Field names, code paths and placeholders (``grand_total``, ``%(company)s``,
  ``{0}``) stay in Latin script. They are identifiers, not prose.
"""

LONG = {
	# ------------------------------------------------------- AGS Core
	"A physical campus, sitting between the legal entity and its school divisions.":
		"حرم مدرسي فعلي، يقع بين الكيان القانوني والمراحل الدراسية التابعة له.",
	"Short code used in naming series and report headers.":
		"رمز مختصر يُستخدم في تسلسل الترقيم وعناوين التقارير.",
	"Parent cost center for every division and department on this campus.":
		"مركز التكلفة الأب لكل مرحلة وقسم في هذا الحرم المدرسي.",
	"Cost Center {0} belongs to company {1}, but this campus belongs to {2}.":
		"مركز التكلفة {0} يتبع الشركة {1}، بينما هذا الحرم المدرسي يتبع {2}.",
	"Cannot delete: {0} school division(s) still reference this campus.":
		"تعذر الحذف: ما زالت {0} مرحلة دراسية مرتبطة بهذا الحرم المدرسي.",
	"From Grade ({0}) is above To Grade ({1}).":
		"الصف (من) {0} أعلى من الصف (إلى) {1}.",
	"Campus row scoping. A user with no scope row sees no campus-bound records.":
		"تحديد نطاق السجلات حسب الحرم المدرسي. المستخدم بلا نطاق محدد لا يرى أي "
		"سجلات مرتبطة بحرم مدرسي.",
	"Group-level roles (CEO, CFO, Auditor) normally have this set.":
		"الأدوار على مستوى المجموعة (الرئيس التنفيذي، المدير المالي، المراجع) "
		"عادةً ما يكون هذا الخيار مفعّلاً لديها.",
	"Grant at least one campus, or tick Access All Campuses.":
		"امنح حرماً مدرسياً واحداً على الأقل، أو فعّل خيار الوصول إلى جميع الأحرام.",
	"Default Campus {0} is not in the granted campus list.":
		"الحرم المدرسي الافتراضي {0} غير مدرج ضمن الأحرام الممنوحة.",
	"Tuition collected up front is parked in a liability and released monthly (SKILL sec. 5.4).":
		"الرسوم الدراسية المحصلة مقدماً تُقيَّد كالتزام ويُعترف بها شهرياً "
		"(SKILL sec. 5.4).",
	"Approved requests and open orders consume budget before the invoice lands (SKILL sec. 7.1).":
		"الطلبات المعتمدة وأوامر الشراء المفتوحة تستهلك الميزانية قبل ورود "
		"الفاتورة (SKILL sec. 7.1).",
	"Comma separated. Supported: In-App, Email, SMS, WhatsApp.":
		"مفصولة بفواصل. المدعوم: داخل التطبيق، البريد الإلكتروني، رسالة نصية، واتساب.",
	"Comma separated: In-App, Email, SMS, WhatsApp.":
		"مفصولة بفواصل: داخل التطبيق، البريد الإلكتروني، رسالة نصية، واتساب.",
	"Phase-2 clearance. Requires certificates in AGS ZATCA Settings.":
		"تصديق المرحلة الثانية. يتطلب شهادات مُعدّة في إعدادات الفوترة الإلكترونية.",
	"Academic Range": "النطاق الدراسي",

	# ------------------------------------------------------- AGS Fees
	"One payer, many children. Consolidates sibling receivables (SKILL sec. 18).":
		"دافع واحد لعدة أبناء. يوحّد ذمم الأشقاء في حساب واحد (SKILL sec. 18).",
	"The receivable entity. One customer per payer keeps sibling invoices on a single statement.":
		"الجهة المدينة. عميل واحد لكل دافع يُبقي فواتير الأشقاء في كشف حساب واحد.",
	"Customer {0} is already used by payer account {1}. One customer per payer keeps sibling invoices on a single statement.":
		"العميل {0} مستخدم بالفعل في حساب الدافع {1}. عميل واحد لكل دافع يُبقي "
		"فواتير الأشقاء في كشف حساب واحد.",
	"Portion of this student's fees billed to this payer.":
		"نسبة رسوم هذا الطالب التي تُفوتر على هذا الدافع.",
	"1 = eldest enrolled. Drives sibling discount tiers.":
		"١ = الأكبر سناً بين المسجلين. يحدد شرائح خصم الأشقاء.",
	"2 = second child. Matches the tier table in SKILL sec. 17.6.":
		"٢ = الابن الثاني. مطابق لجدول الشرائح في SKILL sec. 17.6.",
	"Student-specific priced plan: structure + discounts + installments (SKILL sec. 17.5).":
		"خطة مسعّرة خاصة بالطالب: الهيكل + الخصومات + الأقساط (SKILL sec. 17.5).",
	"Pulls the component lines. Amounts stay editable per student.":
		"يجلب بنود الرسوم. تبقى المبالغ قابلة للتعديل لكل طالب.",
	"Maps the fee to its revenue account (SKILL sec. 17.1).":
		"يربط الرسم بحساب الإيراد الخاص به (SKILL sec. 17.1).",
	"Otherwise only the categories listed below are discounted (SKILL sec. 17.6).":
		"وإلا فلن تُخصم سوى الفئات المدرجة أدناه (SKILL sec. 17.6).",
	"Percent of the eligible base, or a flat amount.":
		"نسبة مئوية من الأساس المشمول، أو مبلغ ثابت.",
	"Caps the computed discount. Zero means uncapped.":
		"يحدد سقف الخصم المحتسب. الصفر يعني بلا سقف.",
	"Lower runs first. Order matters once discounts stack.":
		"الأقل يُطبق أولاً. الترتيب مهم عند تجميع الخصومات.",
	"If unticked, this rule wins alone and suppresses the rest.":
		"عند عدم التحديد، تُطبق هذه القاعدة وحدها وتلغي بقية القواعد.",
	"Early payment discount only holds if settled by this date.":
		"خصم السداد المبكر ساري فقط إذا تم السداد قبل هذا التاريخ.",
	"Audited discount request with before/after values (SKILL sec. 17.7).":
		"طلب خصم موثّق يحتفظ بالقيم قبل وبعد التعديل (SKILL sec. 17.7).",
	"Drives which approval tier applies (SKILL sec. 17.7).":
		"يحدد شريحة الاعتماد المطبقة (SKILL sec. 17.7).",
	"Optional. Leave blank for a one-off exception.":
		"اختياري. اتركه فارغاً للاستثناء لمرة واحدة.",
	"Student {0} is not listed on payer account {1}. Add the child there first.":
		"الطالب {0} غير مدرج في حساب الدافع {1}. أضف الابن هناك أولاً.",
	"Installments total {0} does not match the net payable {1}.":
		"إجمالي الأقساط {0} لا يطابق الصافي المستحق {1}.",
	"Installment {0} is already invoiced as {1}.":
		"القسط {0} تمت فوترته بالفعل ضمن {1}.",
	"Fee category {0} has no linked Item, so it cannot post to a revenue account.":
		"فئة الرسوم {0} غير مرتبطة بصنف، لذا لا يمكن ترحيلها إلى حساب إيراد.",
	"Invoice company {0} does not match the fee plan company {1}.":
		"شركة الفاتورة {0} لا تطابق شركة خطة الرسوم {1}.",
	"Fee plan {0} is in {1} but {2} bills in {3}. Run `bench --site &lt;site&gt; migrate` to align existing plans.":
		"خطة الرسوم {0} بعملة {1} بينما {2} تفوتر بعملة {3}. نفّذ "
		"`bench --site &lt;site&gt; migrate` لمواءمة الخطط الحالية.",
	"Discount amount must be greater than zero.":
		"يجب أن يكون مبلغ الخصم أكبر من صفر.",
	"Discount of {0} exceeds the {1} still uninvoiced on this plan. Raise a credit note against the issued invoices instead.":
		"الخصم {0} يتجاوز المبلغ غير المفوتر {1} في هذه الخطة. أصدر إشعاراً دائناً "
		"على الفواتير الصادرة بدلاً من ذلك.",
	"Discount application {0} approved. Net payable {1} -> {2}.":
		"تم اعتماد طلب الخصم {0}. الصافي المستحق {1} ← {2}.",
	"This discount has already been applied to {0}. Raise a new application to reverse it.":
		"تم تطبيق هذا الخصم بالفعل على {0}. أصدر طلباً جديداً لعكسه.",
	"The waiver posts a credit note against this invoice.":
		"يصدر الإعفاء إشعاراً دائناً على هذه الفاتورة.",
	"Waiver of {0} exceeds the {1} outstanding on invoice {2}.":
		"الإعفاء {0} يتجاوز المبلغ المتبقي {1} في الفاتورة {2}.",
	"Waiver of {0} exceeds the {1} outstanding.":
		"الإعفاء {0} يتجاوز المبلغ المتبقي {1}.",
	"Invoice {0} is billed to {1}, not to this payer account.":
		"الفاتورة {0} مفوترة على {1}، وليس على حساب الدافع هذا.",
	"No Fee Structure matches {0} / {1}; fee plan not created.":
		"لا يوجد هيكل رسوم مطابق لـ {0} / {1}؛ لم تُنشأ خطة الرسوم.",
	"No payer account on student {0}; fee plan not created.":
		"لا يوجد حساب دافع للطالب {0}؛ لم تُنشأ خطة الرسوم.",
	"Set the Deferred Tuition Revenue Account in AGS Settings first.":
		"حدّد حساب الإيرادات الدراسية المؤجلة في إعدادات النظام أولاً.",
	"Set on a generated late-fee invoice. Guarantees one late fee per overdue invoice.":
		"يُضبط على فاتورة رسوم التأخير المُنشأة. يضمن رسم تأخير واحد لكل فاتورة متأخرة.",
	"Fee Components": "بنود الرسوم",
	"Fee Plan": "خطة الرسوم",

	# ------------------------------------------------- AGS Collections
	"Live receivable case per payer, refreshed nightly from the AR ledger (SKILL sec. 20).":
		"ملف تحصيل حي لكل دافع، يُحدَّث ليلياً من دفتر الذمم المدينة (SKILL sec. 20).",
	"This case still has {0} overdue. Use 'Written Off' if the debt is being written off, or collect the balance first.":
		"ما زال في هذا الملف {0} متأخر. استخدم حالة \"مشطوب\" إذا كان الدين "
		"سيُشطب، أو حصّل الرصيد أولاً.",
	"rule + invoice + scheduled day. Guarantees one send per rule per day.":
		"القاعدة + الفاتورة + اليوم المجدول. يضمن إرسالاً واحداً لكل قاعدة يومياً.",

	# ------------------------------------------------ AGS Procurement
	"Side ledger of budget consumed by approved requests and open orders. Never posts to the GL.":
		"دفتر جانبي للميزانية المستهلكة بالطلبات المعتمدة وأوامر الشراء المفتوحة. "
		"لا يُرحَّل إلى الأستاذ العام إطلاقاً.",
	"Weighted score only. The award below stays a human decision (SKILL sec. 8.4).":
		"نتيجة مرجحة فقط. تبقى الترسية أدناه قراراً بشرياً (SKILL sec. 8.4).",
	"Ranking is advisory. The award remains a human decision (SKILL sec. 8.4).":
		"الترتيب استرشادي. تبقى الترسية قراراً بشرياً (SKILL sec. 8.4).",
	"Required when the award differs from the recommendation.":
		"مطلوب عند اختلاف الترسية عن التوصية.",
	"Award justification is required when the award differs from the system recommendation ({0}).":
		"مبرر الترسية مطلوب عند اختلافها عن توصية النظام ({0}).",
	"Awarded supplier {0} is not among the compared suppliers.":
		"المورد المرسى عليه {0} ليس ضمن الموردين المقارَنين.",
	"The awarded supplier has no linked Supplier Quotation to convert.":
		"المورد المرسى عليه ليس لديه عرض سعر مرتبط لتحويله.",
	"Scoring weights must total 100%. They currently total {0}%.":
		"يجب أن يكون مجموع أوزان التقييم ١٠٠٪. المجموع الحالي {0}٪.",
	"Raised automatically when PO / GRN / Invoice disagree (SKILL sec. 8.6).":
		"يُنشأ تلقائياً عند اختلاف أمر الشراء / الاستلام / الفاتورة (SKILL sec. 8.6).",
	"Supplier bill {0} is already booked as {1}.":
		"فاتورة المورد {0} مُقيَّدة بالفعل باسم {1}.",
	"Invoiced rate {0} exceeds ordered rate {1} by {2}%.":
		"السعر المفوتر {0} يتجاوز السعر المطلوب {1} بنسبة {2}٪.",
	"Billing {0} against an ordered value of {1}.":
		"فوترة {0} مقابل قيمة مطلوبة {1}.",
	"Budget exceeded for {0} / {1}. Available {2} (budget {3} less actual {4} and committed {5}), requested {6}.":
		"تجاوز الميزانية لـ {0} / {1}. المتاح {2} (الميزانية {3} ناقص الفعلي {4} "
		"والمرتبط {5})، المطلوب {6}.",
	"Budget exceeded for {0} / {1}. Available {2}, order {3}.":
		"تجاوز الميزانية لـ {0} / {1}. المتاح {2}، أمر الشراء {3}.",
	"Original budget less actuals, open orders and approved requests.":
		"الميزانية الأصلية ناقص الفعلي وأوامر الشراء المفتوحة والطلبات المعتمدة.",
	"Set by the AGS approval matrix. A Purchase Order cannot be raised until this reads Approved.":
		"تُضبط بواسطة مصفوفة الاعتماد. لا يمكن إصدار أمر شراء حتى تصبح الحالة معتمداً.",
	"Field read for threshold routing, e.g. grand_total or discount_percent.":
		"الحقل المقروء لتوجيه الاعتماد حسب الحد، مثل grand_total أو discount_percent.",
	"{0} blocking three-way match exception(s) on this invoice:<br>{1}":
		"{0} استثناء مانع في المطابقة الثلاثية على هذه الفاتورة:<br>{1}",

	# -------------------------------------------------- AGS Inventory
	"School-facing 'Issue Materials'. Posts a Stock Entry of type Material Issue (SKILL sec. 9.5).":
		"واجهة \"صرف المواد\" المدرسية. تُرحّل حركة مخزون من نوع صرف مواد "
		"(SKILL sec. 9.5).",
	"Carries the consumption cost. Defaults from the department.":
		"يحمل تكلفة الاستهلاك. يُستمد افتراضياً من القسم.",
	"The native Material Issue this document posts.":
		"حركة صرف المواد الأصلية التي يُرحّلها هذا المستند.",
	"Row {0}: quantity must be greater than zero.":
		"الصف {0}: يجب أن تكون الكمية أكبر من صفر.",
	"Row {0}: only {1} {2} of {3} available in {4}.":
		"الصف {0}: يتوفر فقط {1} {2} من {3} في {4}.",

	# ----------------------------------------------------- AGS Assets
	"Custody transfer with digital acknowledgement. Blocks separation while open (SKILL sec. 10.4).":
		"نقل عهدة مع إقرار رقمي. يمنع إنهاء الخدمة ما دام مفتوحاً (SKILL sec. 10.4).",
	"Select the employee receiving the assets.": "اختر الموظف المستلم للأصول.",
	"Select the location the assets are returning to.":
		"اختر الموقع الذي ستُرجع إليه الأصول.",
	"A transfer needs both a from and a to employee.":
		"النقل يتطلب تحديد الموظف المرسل والمستلم معاً.",
	"Asset {0} is currently held by {1}. Record a return or a transfer instead.":
		"الأصل {0} في عهدة {1} حالياً. سجّل إرجاعاً أو نقلاً بدلاً من ذلك.",
	"{0} still holds assets under handover(s) {1}. Return or reassign them before completing separation.":
		"ما زال لدى {0} عهد ضمن {1}. أرجعها أو أعد إسنادها قبل إتمام إنهاء الخدمة.",

	# --------------------------------------------------------- AGS HR
	"Iqama and contract expiry tracking with scheduled reminders (SKILL sec. 11.2/35).":
		"تتبع انتهاء الإقامة والعقود مع تذكيرات مجدولة (SKILL sec. 11.2/35).",
	"Iqama / National ID must be 10 digits starting with 1 (citizen) or 2 (resident). Got {0}.":
		"يجب أن تتكون الهوية الوطنية / الإقامة من ١٠ أرقام تبدأ بـ ١ (مواطن) أو "
		"٢ (مقيم). المُدخل: {0}.",
	"Iqama / National ID {0} already belongs to employee {1}.":
		"الهوية الوطنية / الإقامة {0} تخص الموظف {1} بالفعل.",

	# -------------------------------------------------- AGS Approvals
	"One configurable engine for every approval in the system (SKILL sec. 23).":
		"محرك واحد قابل للتهيئة لكل اعتمادات النظام (SKILL sec. 23).",
	"Optional. Pins the level to one person instead of the whole role.":
		"اختياري. يثبّت المستوى على شخص واحد بدلاً من الدور بأكمله.",
	"Optional Python expression over `doc`. Example: doc.campus == 'Jeddah'.":
		"تعبير Python اختياري يُطبّق على `doc`. مثال: doc.campus == 'Jeddah'.",
	"Your role does not permit the analysis '{0}'.":
		"دورك لا يسمح بتشغيل التحليل '{0}'.",

	# ------------------------------------------------- AGS Dashboards
	"Stable machine key, e.g. revenue_per_student.":
		"مفتاح ثابت للنظام، مثل revenue_per_student.",
	"Dotted path resolved against the ags_edusmart KPI registry.":
		"مسار منقوط يُحل من سجل مؤشرات الأداء في ags_edusmart.",
	"Read-only SELECT. Placeholders: %(company)s, %(campus)s, %(from_date)s, %(to_date)s.":
		"استعلام SELECT للقراءة فقط. المتغيرات: %(company)s، %(campus)s، "
		"%(from_date)s، %(to_date)s.",
	"The scheduler recomputes at most this often; dashboards read the snapshot.":
		"يعيد المجدول الاحتساب بهذا المعدل كحد أقصى؛ ولوحات المتابعة تقرأ اللقطة.",
	"Empty means every role that can read the dashboard.":
		"الفراغ يعني كل دور يستطيع قراءة لوحة المتابعة.",
	"code + every dimension. One row per scope, upserted on refresh.":
		"الرمز + كل الأبعاد. صف واحد لكل نطاق، يُحدَّث عند إعادة الاحتساب.",

	# ---------------------------------------------- AGS Notifications
	"Durable queue. The dispatcher drains it so a failing gateway never blocks a transaction.":
		"طابور دائم. يفرّغه الموزّع بحيث لا تُعطّل بوابة متعطلة أي معاملة.",
	"Fieldname holding a User, Employee or Payer Account.":
		"اسم الحقل الذي يحمل مستخدماً أو موظفاً أو حساب دافع.",
	"Jinja context: payer, student, invoice, amount, due_date, days.":
		"متغيرات Jinja: payer، student، invoice، amount، due_date، days.",
	"Jinja over `doc`. Example: PO {{ doc.name }} awaiting approval.":
		"تعبير Jinja على `doc`. مثال: أمر الشراء {{ doc.name }} بانتظار الاعتماد.",

	# ------------------------------------------------ AGS Localization
	"Immutable clearance archive, one row per invoice (SKILL sec. 25.1).":
		"أرشيف تصديق غير قابل للتعديل، صف واحد لكل فاتورة (SKILL sec. 25.1).",
	"Set from the current ZATCA technical spec at deploy time; never hardcoded in code (SKILL sec. 25.1).":
		"يُضبط من المواصفة الفنية الحالية لهيئة الزكاة والضريبة والجمارك عند "
		"النشر؛ ولا يُثبّت في الشيفرة إطلاقاً (SKILL sec. 25.1).",
	"Off by default: a gateway outage should not stop the cashier.":
		"معطّل افتراضياً: انقطاع البوابة يجب ألا يوقف أمين الصندوق.",
	"PIH. Chains invoices so tampering is detectable.":
		"بصمة الفاتورة السابقة. تربط الفواتير في سلسلة تجعل أي تلاعب قابلاً للكشف.",

	# --------------------------------------------------------- AGS AI
	"Off by default. Every figure is computed from the ledger either way; a model only rephrases a finished result and can never query data or invent a number.":
		"معطّل افتراضياً. كل رقم يُحتسب من الدفاتر في الحالتين؛ النموذج يعيد صياغة "
		"نتيجة جاهزة فقط، ولا يمكنه الاستعلام عن البيانات أو اختلاق رقم.",
	"The query log records who ran which analysis and under what scope, including refusals. Refusals are the useful half: a run of them is how you notice someone probing outside their scope.":
		"يسجل سجل الاستعلامات من شغّل أي تحليل وضمن أي نطاق، بما في ذلك حالات "
		"الرفض. حالات الرفض هي النصف المفيد: تكرارها هو ما يكشف محاولة الوصول "
		"خارج النطاق المصرح به.",
	"Who asked which analysis, under what scope. Includes refusals.":
		"من طلب أي تحليل وضمن أي نطاق. يشمل حالات الرفض.",
	"Unticked means the analysis was refused for this user.":
		"عدم التحديد يعني أن التحليل رُفض لهذا المستخدم.",
	"No campus is granted to your account, so no data can be reported. Ask an administrator to set up your AGS User Scope.":
		"لا يوجد حرم مدرسي ممنوح لحسابك، لذا لا يمكن عرض أي بيانات. اطلب من "
		"المسؤول إعداد نطاق صلاحيتك.",
	"No payer account is linked to your login. Contact the school office.":
		"لا يوجد حساب دافع مرتبط بحسابك. تواصل مع إدارة المدرسة.",
	"No active employee record is linked to your login.":
		"لا يوجد سجل موظف نشط مرتبط بحسابك.",
	"I could not match that to an analysis I can run. Here is what I can answer for you.":
		"لم أتمكن من مطابقة ذلك مع تحليل أستطيع تشغيله. إليك ما يمكنني الإجابة عنه.",
	"{0} carries no campus field, so this figure is group-wide rather than restricted to your campuses.":
		"{0} لا يحتوي على حقل حرم مدرسي، لذا هذا الرقم على مستوى المجموعة وليس "
		"مقتصراً على أحرامك المدرسية.",
	"A class average reflects intake, subject and cohort as well as teaching. Treat this as a variance to investigate, not a judgement.":
		"متوسط الفصل يعكس القبول والمادة والدفعة إضافةً إلى التدريس. تعامل معه "
		"كانحراف يستدعي الدراسة، لا كحكم.",
	"Recovery on the overdue book is estimated at half the observed collection rate. Adjust once the school has its own history.":
		"يُقدَّر تحصيل المتأخرات بنصف معدل التحصيل الملاحظ. عدّله عندما يتوفر "
		"سجل تاريخي خاص بالمدرسة.",
	"Based on current salary structure assignments. Does not include planned hires, promotions or end-of-service provisions.":
		"بناءً على هياكل الرواتب المسندة حالياً. لا يشمل التعيينات المخططة أو "
		"الترقيات أو مخصصات نهاية الخدمة.",
	"Projected from historical payslips, so it carries last year's headcount rather than today's.":
		"مُتوقَّع من مسيّرات الرواتب التاريخية، لذا يحمل عدد موظفي العام الماضي "
		"وليس الحالي.",

	# --------------------------------- AI: computed answer sentences
	"{0} is outstanding across {1} payer account(s); {2} of that is already overdue.":
		"يوجد {0} متبقٍ على {1} حساب دافع؛ منها {2} متأخرة السداد بالفعل.",
	"{0} carries the highest overdue balance at {1}, which is {2}% of what has been billed there.":
		"{0} لديه أعلى رصيد متأخر بمبلغ {1}، أي {2}٪ مما تمت فوترته فيه.",
	"Operating margin {0} from {1}% to {2}% year on year ({3} percentage points). Revenue {4}, costs {5}.":
		"هامش التشغيل {0} من {1}٪ إلى {2}٪ على أساس سنوي ({3} نقطة مئوية). "
		"الإيرادات {4}، التكاليف {5}.",
	"Operating margin is {0}% for {1} → {2}. There is no comparable prior year, so no driver analysis is possible yet.":
		"هامش التشغيل {0}٪ للفترة {1} ← {2}. لا يوجد عام سابق للمقارنة، لذا لا "
		"يمكن تحليل المحركات بعد.",
	"Revenue is {0} for {1} → {2}, {3} year on year.":
		"الإيرادات {0} للفترة {1} ← {2}، {3} على أساس سنوي.",
	"{0} account(s) are over budget for {1}, by {2} in total. The largest is {3} at {4} over ({5}%).":
		"{0} حساب تجاوز ميزانيته لـ {1}، بإجمالي {2}. الأكبر هو {3} بتجاوز {4} "
		"({5}٪).",
	"No account is over budget on actuals. {0} line(s) would exceed budget once open commitments are included.":
		"لا يوجد حساب تجاوز ميزانيته فعلياً. {0} بند سيتجاوز الميزانية عند احتساب "
		"الارتباطات المفتوحة.",
	"No fiscal year covers today, so budgets cannot be evaluated.":
		"لا توجد سنة مالية تغطي تاريخ اليوم، لذا لا يمكن تقييم الميزانيات.",
	"About {0} is expected over the next {1} month(s): {2} from the {3} falling due at the observed {4}% collection rate, plus an estimated {5} recovered from the {6} already overdue.":
		"يُتوقع تحصيل نحو {0} خلال {1} شهر: {2} من المستحق البالغ {3} بمعدل "
		"التحصيل الملاحظ {4}٪، إضافةً إلى {5} تقديرياً من المتأخرات البالغة {6}.",
	"Overall collection is {0}% of {1} billed. The weakest campus is {2} at {3}%, with {4} more than 90 days overdue.":
		"إجمالي التحصيل {0}٪ من {1} مفوترة. الأضعف هو {2} بنسبة {3}٪، مع {4} "
		"متأخرة أكثر من ٩٠ يوماً.",
	"{0} payer(s) are more than {1} days overdue, owing {2} between them. The largest is {3} at {4}, {5} days past due.":
		"{0} دافع متأخرون أكثر من {1} يوماً، بإجمالي {2}. الأكبر هو {3} بمبلغ "
		"{4}، متأخر {5} يوماً.",
	"{0} supplier(s) were used. {1} ranks highest: {2}% of orders completed, {3} days average lead time, {4} invoice mismatch(es) across {5} order(s).":
		"تم التعامل مع {0} مورد. {1} في المرتبة الأولى: {2}٪ من الأوامر مكتملة، "
		"متوسط مدة توريد {3} يوماً، و{4} حالة عدم تطابق فواتير عبر {5} أمر.",
	"{0} order(s) are late, with about {1} still undelivered. The worst is {2} from {3}, {4} days past its required date.":
		"{0} أمر شراء متأخر، بقيمة {1} تقريباً لم تُسلَّم بعد. الأسوأ هو {2} من "
		"{3}، متأخر {4} يوماً عن تاريخه المطلوب.",
	"{0} item(s) were last bought more than {1}% above their average price. The largest gap is {2}, last bought at {3} against an average of {4} ({5}% higher).":
		"{0} صنف اشتُري آخر مرة بأعلى من متوسط سعره بأكثر من {1}٪. أكبر فارق هو "
		"{2}، اشتُري بـ {3} مقابل متوسط {4} (أعلى بـ {5}٪).",
	"Not enough repeat purchases in this period to compare prices. An item needs at least two orders.":
		"لا توجد مشتريات متكررة كافية في هذه الفترة لمقارنة الأسعار. يحتاج الصنف "
		"إلى أمرَي شراء على الأقل.",
	"{0} item(s) were requested on more than one separate request in the last {1} days. {2} leads with {3} requests totalling {4} units - buying those together would consolidate the order.":
		"{0} صنف طُلب في أكثر من طلب منفصل خلال {1} يوماً الماضية. {2} في "
		"المقدمة بـ {3} طلبات بإجمالي {4} وحدة - شراؤها معاً يوحّد الأمر.",
	"{0} item(s) are forecast to run out within {1} days at current usage. The most urgent is {2}, with {3} left and about {4} days of cover.":
		"{0} صنف يُتوقع نفاده خلال {1} يوماً بمعدل الاستهلاك الحالي. الأكثر "
		"إلحاحاً هو {2}، بكمية متبقية {3} وتغطية نحو {4} يوماً.",
	"No stock has been issued in the last 90 days, so no consumption rate can be measured yet.":
		"لم تُصرف أي مواد خلال ٩٠ يوماً الماضية، لذا لا يمكن قياس معدل الاستهلاك بعد.",
	"{0} department(s) consume unusually more than the rest. {1} is the clearest, at {2} against a median of {3}.":
		"{0} قسم يستهلك أكثر من غيره بشكل غير معتاد. الأوضح هو {1}، بمبلغ {2} "
		"مقابل وسيط {3}.",
	"Only {0} department(s) have issued stock in this period. At least three are needed before one can be called unusual.":
		"صرف {0} قسم فقط مواد في هذه الفترة. يلزم ثلاثة أقسام على الأقل قبل "
		"وصف أحدها بأنه غير معتاد.",
	"{0} item(s) worth {1} have not moved in {2} months. The largest holding is {3} at {4}.":
		"{0} صنف بقيمة {1} لم تتحرك خلال {2} أشهر. أكبر رصيد هو {3} بقيمة {4}.",
	"Absence runs at {0}% overall and no department stands out against the others.":
		"معدل الغياب {0}٪ إجمالاً ولا يوجد قسم يبرز عن غيره.",
	"Absence runs at {0}% overall. {1} department(s) are unusually high; {2} is the clearest at {3}% against a median of {4}%.":
		"معدل الغياب {0}٪ إجمالاً. {1} قسم مرتفع بشكل غير معتاد؛ الأوضح هو {2} "
		"بنسبة {3}٪ مقابل وسيط {4}٪.",
	"Attendance is recorded for only {0} department(s) in this period - too few to identify an outlier.":
		"الحضور مسجل لـ {0} قسم فقط في هذه الفترة - وهو عدد أقل من أن يحدد حالة شاذة.",
	"{0} active employee(s) on current structures annualise to {1}.":
		"{0} موظف نشط على الهياكل الحالية يعادلون سنوياً {1}.",
	" With {0}% growth applied, next year projects to {1}.":
		" وبتطبيق نمو {0}٪، يُتوقع العام القادم {1}.",
	"No salary structures are assigned and no payslips have been posted, so payroll cannot be projected.":
		"لا توجد هياكل رواتب مسندة ولا مسيّرات رواتب مرحّلة، لذا لا يمكن توقع الرواتب.",
	"No current salary structure assignments exist. Based on the last 12 months of posted payslips, payroll is running at {0} a year.":
		"لا توجد هياكل رواتب مسندة حالياً. بناءً على مسيّرات آخر ١٢ شهراً، تبلغ "
		"الرواتب {0} سنوياً.",
	"{0} document(s) expire within {1} days, of which {2} have already expired. Soonest: {3}'s {4} on {5}.":
		"{0} مستند ينتهي خلال {1} يوماً، منها {2} منتهية بالفعل. الأقرب: {4} "
		"الخاص بـ {3} بتاريخ {5}.",
	"{0} student(s) are below {1}% attendance. The lowest is {2} at {3}% ({4} absences from {5} recorded days).":
		"{0} طالب دون نسبة حضور {1}٪. الأدنى هو {2} بنسبة {3}٪ ({4} غياباً من "
		"{5} يوماً مسجلاً).",
	"No student has at least {0} attendance records in this period, so attendance risk cannot be assessed.":
		"لا يوجد طالب لديه {0} سجل حضور على الأقل في هذه الفترة، لذا لا يمكن "
		"تقييم خطر الغياب.",
	"{0} class(es) show a lower average than the previous period. The largest fall is {1}, from {2}% to {3}% ({4} points).":
		"{0} فصل يُظهر متوسطاً أقل من الفترة السابقة. أكبر انخفاض هو {1}، من "
		"{2}٪ إلى {3}٪ ({4} نقطة).",
	"There are not two comparable periods of assessment results yet, so a trend cannot be measured.":
		"لا توجد فترتان قابلتان للمقارنة من نتائج التقييم بعد، لذا لا يمكن قياس الاتجاه.",
	"The school average is {0}%. {1} class(es) sit more than {2} points below it. The widest gap is {3} ({4}) at {5}%, {6} points below.":
		"متوسط المدرسة {0}٪. {1} فصل يقل عنه بأكثر من {2} نقطة. أوسع فارق هو "
		"{3} ({4}) بنسبة {5}٪، أي أقل بـ {6} نقطة.",
	"Only {0} class-instructor combination(s) have at least five results, which is too few to compare against a school average.":
		"يوجد {0} اقتران بين فصل ومعلم لديه خمس نتائج على الأقل، وهو عدد أقل من "
		"أن يقارن بمتوسط المدرسة.",
	"No department stands out: consumption is evenly spread across {0} departments.":
		"لا يوجد قسم شاذ: الاستهلاك موزع بالتساوي على {0} قسماً.",

	# ------------------------------------------------------ stragglers
	"Principal": "المدير",
	"Warning": "تحذير",
	"Financial payer. Kept separate from the student identity (SKILL sec. 13.4).":
		"الدافع المالي. يُحفظ منفصلاً عن هوية الطالب (SKILL sec. 13.4).",
	"Used to build the fee plan on enrollment.":
		"يُستخدم لبناء خطة الرسوم عند التسجيل.",
}
