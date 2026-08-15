# Payment Rules

Agents must not record payment as confirmed from POP alone, change prices autonomously, approve deposits/final balances, create financial records without approved rails, or promise refunds/cancellations without approved policy.

Every sale-bound receipt uses one owner-authenticated canonical action: enter
the actual amount received, preview the exact current sale/payment evidence,
then confirm that digest-bound preview. A full payment must equal the canonical
amount due. A partial payment preserves the actual lesser amount. Preview
writes nothing; confirmation rechecks locked Supabase state and binds replay to
the preserved digest. Legacy direct payment updates fail closed. Telegram may
link to review but must not claim recording before canonical readback.
