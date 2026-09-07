select 'DocPerm' src, role, `read` from `tabDocPerm`
  where parent='AGS Payer Account'
union all
select 'Custom' src, role, `read` from `tabCustom DocPerm`
  where parent='AGS Payer Account';
