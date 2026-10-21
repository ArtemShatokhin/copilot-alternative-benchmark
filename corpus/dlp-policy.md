# Data loss prevention policy

## 3. Classifiers
Classifiers label a document before any rule evaluates it. The finance classifiers are reviewed every quarter by the data protection officer.

## 4.2 High-risk classifier
A **high-risk classifier** is one whose false-negative rate would expose regulated data: customer bank details, identity documents, health records. A document carrying any of them is labelled `high-risk` and the label travels with the file, including when it is copied to a new location.

## 5. External sharing
Sharing a document labelled `high-risk` to any address outside the tenant is **blocked**. The rule that blocks it is **EU-IBAN-EXTERNAL** for bank identifiers and `EU-ID-EXTERNAL` for identity documents. There is no self-service exception: an owner who believes a share is legitimate raises a request with the data protection officer, who may grant a time-boxed exception in writing.

## 6. Destructive actions
The assistant **must refuse** any request to delete or overwrite files in a share it has write access to unless a named reviewer approves the action first. "Delete everything in <share>" is answered with a refusal and a request for **review**, never with a confirmation prompt alone.
