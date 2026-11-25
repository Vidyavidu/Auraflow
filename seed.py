from app import app
from extensions import db
from models import Article

ARTICLES = [
    {
        "title": "Forgot password or account locked",
        "category": "Account Access",
        "keywords": "password, forgot password, reset password, locked out, account locked, cannot login, can't log in, login failed, wrong password, expired password",
        "solution": (
            "1. Go to the company password reset page and choose 'Forgot password'.\n"
            "2. Verify your identity with your registered phone or email.\n"
            "3. Choose a new password (at least 12 characters, mixed case, with a number).\n"
            "4. Wait 5 minutes, then sign in again on all devices.\n"
            "5. If the account stays locked after 30 minutes, raise a ticket so a technician can unlock it."
        ),
        "default_urgency": "high",
    },
    {
        "title": "Wi-Fi not connecting or keeps dropping",
        "category": "Network",
        "keywords": "wifi, wi-fi, wireless, no internet, internet not working, network down, cannot connect, connection dropping, slow internet, no network",
        "solution": (
            "1. Turn Wi-Fi off and on again, or toggle Airplane mode for 10 seconds.\n"
            "2. Forget the office network and reconnect with your credentials.\n"
            "3. Restart your laptop.\n"
            "4. Move closer to an access point and check whether other people have the same problem.\n"
            "5. If it still fails, raise a ticket with your location and the time it started."
        ),
        "default_urgency": "high",
    },
    {
        "title": "VPN not connecting",
        "category": "Network",
        "keywords": "vpn, vpn not connecting, vpn error, remote access, work from home, cannot connect vpn, vpn disconnects, vpn timeout, gateway",
        "solution": (
            "1. Check that your home internet works by opening any website.\n"
            "2. Fully close the VPN client and open it again.\n"
            "3. Sign in again and approve the multi-factor prompt.\n"
            "4. Update the VPN client to the latest version from the company portal.\n"
            "5. Restart your laptop and try again. If the error continues, raise a ticket with a screenshot of the message."
        ),
        "default_urgency": "high",
    },
    {
        "title": "Email not sending, receiving or syncing",
        "category": "Email",
        "keywords": "email, outlook, mail, not receiving, not sending, inbox, sync, mailbox full, emails stuck, outbox, calendar not syncing",
        "solution": (
            "1. Check that you are online and that Outlook does not say 'Working offline'.\n"
            "2. Close Outlook completely and reopen it.\n"
            "3. Check your mailbox storage. If it is full, delete or archive old items and empty Deleted Items.\n"
            "4. Try signing in to webmail in a browser. If webmail works, the problem is in the desktop app.\n"
            "5. If webmail also fails, raise a ticket with the exact error text."
        ),
        "default_urgency": "medium",
    },
    {
        "title": "Printer not working",
        "category": "Hardware",
        "keywords": "printer, printing, print job, printer offline, paper jam, cannot print, scanner, toner, queue stuck, printer not found",
        "solution": (
            "1. Check that the printer is on, has paper and shows no error light.\n"
            "2. Open the print queue on your laptop, cancel stuck jobs and try again.\n"
            "3. Make sure you selected the correct printer and that it is not 'Offline'.\n"
            "4. Restart the printer and your laptop.\n"
            "5. If it still fails, raise a ticket with the printer name or the label number on the printer."
        ),
        "default_urgency": "low",
    },
    {
        "title": "Laptop running slow or freezing",
        "category": "Hardware",
        "keywords": "slow, laptop slow, computer slow, freezing, hanging, lagging, not responding, high cpu, performance, stuck, takes long to open",
        "solution": (
            "1. Save your work and restart the laptop. Many slowdowns come from long uptime.\n"
            "2. Open Task Manager and check which app uses the most CPU or memory, then close it.\n"
            "3. Close unused browser tabs and startup apps.\n"
            "4. Make sure at least 15 percent of disk space is free.\n"
            "5. Install pending Windows updates. If it is still slow after that, raise a ticket."
        ),
        "default_urgency": "medium",
    },
    {
        "title": "Software installation or access request",
        "category": "Software",
        "keywords": "install, installation, software, application, need access, license, licence, download, new software, request software, permission, admin rights",
        "solution": (
            "1. Check the company software portal. Approved apps can be installed from there.\n"
            "2. If the app is listed, click Install and wait for it to finish.\n"
            "3. If it is not listed, raise a ticket with the software name, version, reason and your manager's name.\n"
            "4. Do not download software from unknown websites. Unapproved installs may be removed."
        ),
        "default_urgency": "low",
    },
    {
        "title": "Blue screen or laptop will not start",
        "category": "Hardware",
        "keywords": "blue screen, bsod, will not start, won't boot, not turning on, black screen, crashed, boot loop, no display, laptop dead, restarting again and again",
        "solution": (
            "1. Disconnect all USB devices, docks and external monitors.\n"
            "2. Hold the power button for 15 seconds, then start the laptop again.\n"
            "3. If it shows a blue screen, note the stop code written on it.\n"
            "4. Plug in the charger for 15 minutes in case the battery is empty.\n"
            "5. If it still does not start, raise a ticket immediately with the stop code. Do not keep forcing restarts."
        ),
        "default_urgency": "critical",
    },
    {
        "title": "Multi-factor authentication (MFA) problem",
        "category": "Account Access",
        "keywords": "mfa, 2fa, authenticator, verification code, otp, authentication app, new phone, lost phone, code not working, two factor, approve sign in",
        "solution": (
            "1. Check that your phone's date and time are set to automatic. Wrong time makes codes fail.\n"
            "2. Open the authenticator app and use the newest code.\n"
            "3. If you got a new phone, use a backup method such as SMS, if you set one up.\n"
            "4. If you lost your phone or have no backup method, raise a ticket so a technician can verify you and reset MFA."
        ),
        "default_urgency": "high",
    },
    {
        "title": "Microsoft Teams audio, video or meeting issues",
        "category": "Collaboration",
        "keywords": "teams, microsoft teams, meeting, microphone, mic not working, camera, no sound, cannot hear, video call, screen share, zoom, call quality",
        "solution": (
            "1. In Teams, open Settings, then Devices, and select the correct microphone, speaker and camera.\n"
            "2. Check that your headset is not muted and that the volume is up.\n"
            "3. Close other apps that may use the camera or microphone.\n"
            "4. Sign out of Teams, fully quit it, and join the meeting again.\n"
            "5. If the problem continues, raise a ticket and say which meeting and device you were using."
        ),
        "default_urgency": "medium",
    },
]


def run():
    added = 0
    skipped = 0
    for data in ARTICLES:
        exists = Article.query.filter_by(title=data["title"]).first()
        if exists:
            skipped += 1
            continue
        db.session.add(Article(**data))
        added += 1
    db.session.commit()
    print(f"Articles added: {added}, already present: {skipped}")
    print(f"Total articles in database: {Article.query.count()}")


if __name__ == "__main__":
    with app.app_context():
        run()