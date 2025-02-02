"""
utils.py

Aims to clean out LLM output, cleans out non-existing HTML tags, and closes open tags
"""

from html.parser import HTMLParser
import httpx
import asyncio
import json

ACCEPTABLE_HTML_TAGS = ["b", "strong", "i", "em", "code", "s", "strike", "del", "pre"]
TEST_CASES = [
    """
    <i>Hello, <b>world!</b></i>""",
    """
    <i>Hello, <b>world!</b>""",
    """
    <i>Hello, <b>world!</i>""",
    """
    Got it! Here's an example of HTML with unmatched tags:
    
    <b>This is a bold text</i>
    <i>This is italic text</b>
    <code>This is inline code</s>
    <s>This is strikethrough text</code>
    
    Let me know if you need
    """,
    """
    Sure! Here's an example of HTML with unmatched tags:
    
    <b>This is a bold text</i>
    <i>This is italic text</b>
    <code>This is inline code</s>
    <s>This is strikethrough text</code>
    
    Let me know if you need further help.
    """
]


def clean_html(html: str) -> str:
    tag_stack = []
    result = ""

    class HTMLCleaner(HTMLParser):
        """
        we can assume no attributes are present in the tags
        """

        def handle_starttag(self, tag, attrs):
            nonlocal result
            if tag in ACCEPTABLE_HTML_TAGS:
                tag_stack.append(tag)
                result += f"<{tag}>"
            else:
                result += f"&lt;{tag}&gt;"

        def handle_endtag(self, tag):
            nonlocal result
            if tag in ACCEPTABLE_HTML_TAGS and tag_stack[-1] == tag:
                tag_stack.pop()
                result += f"</{tag}>"
            else:
                result += f"&lt;/{tag}&gt;"

        def handle_data(self, data):
            nonlocal result
            result += data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parser = HTMLCleaner()
    parser.feed(html)

    result.rstrip(" \n\t")

    # close all open tags
    while len(tag_stack) > 0:
        result += f"</{tag_stack[-1]}>"
        tag_stack.pop()

    return result


WEB_TEST_CASES = [
    """
    <div>
    <h1>Hello, world!</h1>
    <p>This is a paragraph</p>
    <a href="https://www.google.com">Google</a>
    <img src="https://www.google.com/images/branding/googlelogo/1x/googlelogo_color_272x92dp.png" alt="Google Logo">
    <script>
    console.log("Hello, world!");
    </script>
    <style>
    body {
        background-color: red;
    }
    </style>
    </div>
    """
]

TAGS_TO_KEEP = ["body", "h1", "h2", "h3", "h4", "h5", "h6", "p", "a", "ul", "ol", "li", "blockquote", "code", "pre", "table", "thead", "tbody", "tfoot", "tr", "td", "th", "article"]
ATTRIBUTES_TO_KEEP = ["alt"]


def clean_web_html(html: str) -> str:
    """
    Cleans out comments, scripts, css, and other non-content tags and attributes.
    """
    result = ""
    tag_stack = []

    class HTMLCleaner(HTMLParser):
        def handle_starttag(self, tag, attrs):
            nonlocal result
            tag_stack.append(tag)
            if tag in TAGS_TO_KEEP:
                result += f"<{tag}"
                for attr, value in attrs:
                    if attr in ATTRIBUTES_TO_KEEP:
                        result += f" {attr}=\"{value}\""
                result += ">"

        def handle_endtag(self, tag):
            nonlocal result
            tag_stack.pop()
            if tag in TAGS_TO_KEEP:
                result += f"</{tag}>"

        def handle_data(self, data):
            nonlocal result
            if len(tag_stack) and tag_stack[-1] in TAGS_TO_KEEP:
                result += data

    parser = HTMLCleaner()
    parser.feed(html)
    return result


async def get_web_content(url: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text
        #return clean_web_html(response.text)

if __name__ == "__main__":
    for test_case in TEST_CASES:
        print(clean_html(test_case))
        print("-" * 100)

    for test_case in WEB_TEST_CASES:
        print(clean_web_html(test_case))
        print("-" * 100)

    asyncio.run(get_web_content("https://www.google.com"))
