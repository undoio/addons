import dataclasses
import json
import shutil
import tarfile
import tempfile
import uuid
from pathlib import Path

import requests


class LicensingServerError(Exception):

    def __init__(self, message: str) -> None:
        super().__init__(
            f"{message}\n\n"
            f"Consider retrying later. "
            f"If the problem persists, contact Undo support at <support@undo.io>."
        )


LICENSING_SERVER_URL = "https://api.undo.io/licensing/v1/udb/trial-license"
UNDO_LICENSING_API_TOKEN = "aYFFhoiDSvwXzl1mxNFB"


@dataclasses.dataclass(frozen=True)
class LicenseTrialResponse:
    uid: str
    download_url: str


def obtain_individual_evaluation_license() -> LicenseTrialResponse:
    """
    Create a new trial license and return its UID and download URL.
    """
    unique_id = uuid.uuid4().hex[:12]
    try:
        response = requests.post(
            LICENSING_SERVER_URL,
            json={
                "first_name": "Claude Plugin for explain",
                "last_name": "(AI trial)",
                "email": f"claude-plugin+{unique_id}@undo.io",
                "language": "lang_cpp",
                "x_undo_auth": UNDO_LICENSING_API_TOKEN,
            },
            headers={
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LicensingServerError(
            f"Failed to obtain a trial license from the licensing server: {exc}"
        ) from exc

    try:
        response_json = response.json()
    except json.JSONDecodeError as exc:
        raise LicensingServerError(
            f"Invalid JSON response from the licensing server: {exc}"
        ) from exc

    try:
        return LicenseTrialResponse(
            uid=response_json["uid"],
            download_url=response_json["download_url"],
        )
    except KeyError as exc:
        raise LicensingServerError(
            f"Invalid reply from the licensing server, missing key: {exc}"
        ) from exc


def install_trial(dest: Path) -> Path:
    """
    Obtain a new UDB trial license, download the UDB trial, and install it to the specified
    destination.

    Returns the path to the installed UDB trial.
    """
    if dest.exists():
        raise FileExistsError(
            f"A trial was already installed. If you want to use a different Undo installation, "
            f"ask the user to use `/undo:configure_undo_path` to configure an alternative path."
        )

    license_response = obtain_individual_evaluation_license()

    with (
        tempfile.NamedTemporaryFile(
            mode="w+b",
            suffix=".tar.gz",
            prefix=f"undo-download",
        ) as tarball_path,
        # Use a temporary path to avoid partial installations on failure.
        tempfile.TemporaryDirectory(
            dir=dest.parent,
            prefix=f".{dest.name}.",
            suffix=".part",
        ) as tmp_dest,
    ):
        # Download the trial.
        with requests.get(license_response.download_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            r.raw.decode_content = True  # Ensure gzip/deflate are handled.
            with open(tarball_path.name, "wb") as f:
                shutil.copyfileobj(r.raw, f, length=1024 * 1024)

        # Extract it to the temporary location.
        # We need to strip the first component from the path (e.g. `Undo-Suite-x86-X.Y.Z/`).
        strip_components = 1
        with tarfile.open(tarball_path.name, "r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                parts = member.name.split("/")[strip_components:]
                if parts:
                    member.name = "/".join(parts)
                    tar.extract(member, tmp_dest, filter="data")

        # Verify it's a valid UDB package (i.e., UDB is present).
        if not (Path(tmp_dest) / "udb").exists():
            raise FileNotFoundError(f"UDB executable not found in downloaded package.")

        # Finally, move the temporary installation to the final destination.
        Path(tmp_dest).rename(dest)

    installed_udb = dest / "udb"
    # We checked above, so this should not happen.
    assert installed_udb.exists(), "Installed UDB binary not found after trial installation!"
    return installed_udb
