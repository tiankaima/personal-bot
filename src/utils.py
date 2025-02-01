"""
utils.py

Aims to clean out LLM output, cleans out non-existing HTML tags, and closes open tags
"""

from html.parser import HTMLParser

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


if __name__ == "__main__":
    for test_case in TEST_CASES:
        print(clean_html(test_case))
        print("-" * 100)
