import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders


class EmailManager:
    def __init__(self, gmail_user=None, gmail_password=None):
        """
        Initialize EmailManager with Gmail credentials.

        Args:
            gmail_user (str): Gmail email address. If None, will look for GMAIL_USER environment variable.
            gmail_password (str): Gmail password or app password. If None, will look for GMAIL_PASSWORD environment variable.
        """
        self.gmail_user = gmail_user or os.environ.get('GMAIL_USER')
        self.gmail_password = gmail_password or os.environ.get('GMAIL_PASSWORD')

        if not self.gmail_user or not self.gmail_password:
            raise ValueError(
                "Gmail credentials not provided. Set GMAIL_USER and GMAIL_PASSWORD environment variables or pass them as parameters.")

        self.logger = logging.getLogger(__name__)

    def send_email(self, to_email, subject, body, is_html=False, cc=None, bcc=None, attachments=None):
        """
        Send an email using Gmail SMTP.

        Args:
            to_email (str or list): Recipient email address(es).
            subject (str): Email subject.
            body (str): Email body content.
            is_html (bool): If True, the body is treated as HTML.
            cc (str or list): CC recipient(s).
            bcc (str or list): BCC recipient(s).
            attachments (list): List of file paths to attach.

        Returns:
            bool: True if email sent successfully, False otherwise.
        """
        try:
            msg = MIMEMultipart()
            msg['From'] = self.gmail_user

            # Handle to_email as string or list
            if isinstance(to_email, list):
                msg['To'] = ", ".join(to_email)
            else:
                msg['To'] = to_email

            msg['Subject'] = subject

            # Handle CC if provided
            if cc:
                if isinstance(cc, list):
                    msg['Cc'] = ", ".join(cc)
                else:
                    msg['Cc'] = cc

            # Handle BCC if provided
            if bcc:
                if isinstance(bcc, list):
                    msg['Bcc'] = ", ".join(bcc)
                else:
                    msg['Bcc'] = bcc

            # Attach body with appropriate MIME type
            if is_html:
                msg.attach(MIMEText(body, 'html'))
            else:
                msg.attach(MIMEText(body, 'plain'))

            # Attach files if any
            if attachments:
                for file_path in attachments:
                    self._attach_file(msg, file_path)

            # Connect to Gmail SMTP server
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.gmail_user, self.gmail_password)

            # Compile list of all recipients
            all_recipients = []

            # Add primary recipients
            if isinstance(to_email, list):
                all_recipients.extend(to_email)
            else:
                all_recipients.append(to_email)

            # Add CC recipients if any
            if cc:
                if isinstance(cc, list):
                    all_recipients.extend(cc)
                else:
                    all_recipients.append(cc)

            # Add BCC recipients if any
            if bcc:
                if isinstance(bcc, list):
                    all_recipients.extend(bcc)
                else:
                    all_recipients.append(bcc)

            # Send email
            server.sendmail(self.gmail_user, all_recipients, msg.as_string())
            server.quit()

            self.logger.info(f"Email sent successfully to {msg['To']}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send email: {str(e)}")
            return False

    def send_plain_email(self, to_email, subject, body, cc=None, bcc=None, attachments=None):
        """Shorthand method to send plain text email."""
        return self.send_email(to_email, subject, body, False, cc, bcc, attachments)

    def send_html_email(self, to_email, subject, body, cc=None, bcc=None, attachments=None):
        """Shorthand method to send HTML email."""
        return self.send_email(to_email, subject, body, True, cc, bcc, attachments)

    def _attach_file(self, msg, file_path):
        """
        Attach a file to the email.

        Args:
            msg (MIMEMultipart): The email message object.
            file_path (str): Path to the file to attach.
        """
        try:
            with open(file_path, 'rb') as file:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(file.read())

            encoders.encode_base64(part)

            # Set attachment header with filename
            filename = os.path.basename(file_path)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{filename}"'
            )

            msg.attach(part)
            self.logger.debug(f"Attached file: {filename}")

        except Exception as e:
            self.logger.error(f"Failed to attach file {file_path}: {str(e)}")


email_manager = EmailManager()
