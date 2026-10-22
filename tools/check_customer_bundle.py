"""Inspect the actual PyInstaller EXE: vendor-only code must not ship to customers."""
from __future__ import annotations
import argparse
from pathlib import Path

SELLER_ONLY = (
    'windows.vendor_manager', 'tools.vendor_ledger', 'tools.vendor_sales',
    'tools.vendor_backup', 'tools.license_issuer', 'tools.license_revoke',
    'tools.package_unsigned_release', 'tools.payos_webhook_server',
    'tools.einvoice',
)
REQUIRED = ('windows.desktop_window', 'ads_core.licensing')


class BundleAuditError(ValueError):
    pass


def verify_exe(exe: Path) -> dict:
    from PyInstaller.archive.readers import CArchiveReader
    if not Path(exe).is_file():
        raise BundleAuditError('Customer EXE does not exist')
    archive = CArchiveReader(str(exe))
    modules = set(archive.toc)
    pyz = [name for name, entry in archive.toc.items() if entry[-1] == 'z']
    if len(pyz) != 1:
        raise BundleAuditError('Expected one embedded Python PYZ archive')
    inner = archive.open_embedded_archive(pyz[0])
    modules.update(inner.toc)
    leaked = sorted(name for name in modules if any(
        name == prefix or name.startswith(prefix + '.') for prefix in SELLER_ONLY))
    if leaked:
        raise BundleAuditError('Seller-only code included in customer EXE: ' + ', '.join(leaked))
    missing = sorted(set(REQUIRED) - modules)
    if missing:
        raise BundleAuditError('Required customer desktop modules missing: ' + ', '.join(missing))
    return {'safe': True, 'modules_inspected': len(modules)}


def main(argv=None):
    p = argparse.ArgumentParser(description='Inspect real customer EXE bundle')
    p.add_argument('--exe', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        found = verify_exe(args.exe)
    except (BundleAuditError, OSError, ValueError) as exc:
        p.error(str(exc))
    print('PASS: no vendor-only modules in customer EXE; ' +
          str(found['modules_inspected']) + ' bundled members inspected')


if __name__ == '__main__':
    main()
