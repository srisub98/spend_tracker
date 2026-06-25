"""Where uploaded files land on disk.

Uploads are partitioned under UPLOAD_FOLDER so a multi-user / multi-bank setup
stays tidy and auditable:

    data/uploads/<provider>/    transaction CSVs, by the account's institution
    data/uploads/holdings/      brokerage holdings CSVs (account unknown at save)
    data/uploads/statements/    Vanguard statement PDFs

The whole `data/` tree is git-ignored — these are local-only audit copies.
"""
import os
import re
from werkzeug.utils import secure_filename
import config


def provider_slug(account):
    """Filesystem-safe folder name for an account's provider.

    Prefers the institution (e.g. "Chase" -> "chase"), then the account name,
    then its type; falls back to "other" when nothing usable is set.
    """
    raw = ""
    if account is not None:
        raw = account["institution"] or account["name"] or account["type"] or ""
    slug = re.sub(r"[^a-z0-9]+", "-", str(raw).lower()).strip("-")
    return slug or "other"


def upload_path(filename, *, account=None, bucket=None):
    """Path under UPLOAD_FOLDER for `filename`, creating the folder.

    Pass `account` for account-scoped uploads (partitioned by provider) or a
    fixed `bucket` name for uploads where the account isn't known until preview
    (holdings, statements). Reproducible from the same (filename, account) so a
    preview and its later confirm resolve to the same file.
    """
    sub = bucket or provider_slug(account)
    safe = secure_filename(filename) or "upload"
    folder = os.path.join(config.UPLOAD_FOLDER, sub)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, safe)
