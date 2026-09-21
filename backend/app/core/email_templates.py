from html import escape


def render_email(
    *,
    heading: str,
    paragraphs: list[str],
    button_label: str | None = None,
    button_url: str | None = None,
    footer: str | None = None,
) -> tuple[str, str]:
    """
    Builds one email as (plain_text, html) so it can be sent as multipart/alternative:
    clients that render HTML show the button, everything else gets the same content
    with the link on its own line.

    Everything interpolated into the HTML goes through html.escape — task titles and
    names are user-controlled text, and an email is a place where an unescaped `<` is
    an injection bug, not just a display glitch. The HTML is table-based with inline
    styles because that is what mail clients (Gmail, Outlook) reliably render.
    """
    text_parts = [heading, ""]
    for paragraph in paragraphs:
        text_parts += [paragraph, ""]
    if button_label and button_url:
        text_parts += [f"{button_label}: {button_url}", ""]
    if footer:
        text_parts.append(footer)
    plain = "\n".join(text_parts).strip() + "\n"

    paragraphs_html = "".join(
        f'<p style="margin:0 0 16px;font-size:15px;line-height:1.5;color:#374151;">'
        f"{escape(paragraph)}</p>"
        for paragraph in paragraphs
    )
    button_html = ""
    if button_label and button_url:
        safe_url = escape(button_url, quote=True)
        button_html = (
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 24px;">'
            '<tr><td style="background:#4f46e5;border-radius:8px;">'
            f'<a href="{safe_url}" style="display:inline-block;padding:12px 24px;'
            "font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;"
            f'">{escape(button_label)}</a></td></tr></table>'
            '<p style="margin:0 0 16px;font-size:12px;line-height:1.5;color:#6b7280;">'
            f'Button not working? Paste this link into your browser:<br>'
            f'<a href="{safe_url}" style="color:#4f46e5;word-break:break-all;">'
            f"{escape(button_url)}</a></p>"
        )
    footer_html = (
        f'<p style="margin:0;font-size:12px;line-height:1.5;color:#6b7280;">{escape(footer)}</p>'
        if footer
        else ""
    )

    html = (
        '<!doctype html><html><body style="margin:0;padding:24px;background:#f3f4f6;'
        'font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        '<td align="center"><table role="presentation" width="480" cellpadding="0" '
        'cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;'
        'border-radius:12px;border:1px solid #e5e7eb;"><tr><td style="padding:32px;">'
        '<p style="margin:0 0 20px;font-size:18px;font-weight:700;color:#4f46e5;">CollabFlow</p>'
        f'<h1 style="margin:0 0 16px;font-size:20px;color:#111827;">{escape(heading)}</h1>'
        f"{paragraphs_html}{button_html}{footer_html}"
        "</td></tr></table></td></tr></table></body></html>"
    )
    return plain, html
