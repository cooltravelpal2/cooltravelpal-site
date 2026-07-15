<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:atom="http://www.w3.org/2005/Atom">
  <xsl:output method="html" encoding="UTF-8" indent="yes"/>
  <xsl:template match="/rss/channel">
    <html lang="en">
      <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        <title><xsl:value-of select="title"/> — RSS feed</title>
        <style>
          body { margin:0; font-family:-apple-system, "Hanken Grotesk", "Segoe UI", sans-serif; background:#FBFAF6; color:#2A2622; line-height:1.6; }
          .wrap { max-width:720px; margin:0 auto; padding:48px 24px 80px; }
          .note { background:#F1EDE3; border:1px solid #E0D9C8; border-radius:12px; padding:16px 20px; font-size:.95rem; margin:0 0 36px; }
          .note b { color:#7A3B4E; }
          h1 { font-size:1.9rem; margin:0 0 8px; }
          p.desc { color:#6B6459; margin:0 0 28px; }
          .item { border-bottom:1px solid #E7E1D4; padding:22px 0; }
          .item h2 { font-size:1.15rem; margin:0 0 6px; }
          .item a { color:#2C74C9; text-decoration:none; }
          .item a:hover { text-decoration:underline; }
          .date { font-size:.85rem; color:#8A8375; margin:0 0 6px; }
          .item p { margin:0; }
          .home { display:inline-block; margin-top:32px; color:#7A3B4E; font-weight:600; text-decoration:none; }
        </style>
      </head>
      <body>
        <div class="wrap">
          <div class="note">📡 This is the <b>Cool TravelPal RSS feed</b>. Copy this page's address into any RSS reader (Feedly, NetNewsWire, Reeder…) to get every new guide and announcement — including the Museum Knight reveal — the moment it's published.</div>
          <h1><xsl:value-of select="title"/></h1>
          <p class="desc"><xsl:value-of select="description"/></p>
          <xsl:for-each select="item">
            <div class="item">
              <p class="date"><xsl:value-of select="substring(pubDate, 1, 16)"/></p>
              <h2><a href="{link}"><xsl:value-of select="title"/></a></h2>
              <p><xsl:value-of select="description"/></p>
            </div>
          </xsl:for-each>
          <a class="home" href="https://cooltravelpal.com/">← Back to cooltravelpal.com</a>
        </div>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>
