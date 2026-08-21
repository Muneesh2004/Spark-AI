import os
import ast
import math
import operator
import json
import requests
import wikipedia

from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI


# ============================================================
# CONFIGURATION
# ============================================================

SEARCHAPI_API_KEY = os.getenv(
    "SEARCHAPI_API_KEY",
    ""
).strip()

SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"


# ============================================================
# SEARCHAPI.IO / GOOGLE SEARCH
# ============================================================

@tool
def google_search(query: str) -> str:
    """
    Search Google using SearchApi.io.

    Use this tool when the user asks for:
    - current information
    - latest information
    - recent news
    - today's information
    - current events
    - current prices
    - stock prices
    - weather
    - recent technology information
    - software releases
    - company information
    - websites
    - information that may have changed recently

    Do not use internal knowledge for information that
    requires current web data.
    """

    if not SEARCHAPI_API_KEY:
        return (
            "Google search is unavailable because "
            "SEARCHAPI_API_KEY is not configured."
        )

    try:

        response = requests.get(
            SEARCHAPI_URL,
            params={
                "engine": "google",
                "q": query,
                "api_key": SEARCHAPI_API_KEY,
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        results = []

        # ====================================================
        # GOOGLE ANSWER BOX
        # ====================================================

        answer_box = data.get(
            "answer_box"
        )

        if answer_box:

            answer = {
                "type": "answer_box",
                "title": answer_box.get(
                    "title"
                ),
                "answer": answer_box.get(
                    "answer"
                ),
                "snippet": answer_box.get(
                    "snippet"
                ),
            }

            organic_result = (
                answer_box.get(
                    "organic_result"
                )
            )

            if organic_result:

                answer["source"] = (
                    organic_result.get(
                        "source"
                    )
                )

                answer["link"] = (
                    organic_result.get(
                        "link"
                    )
                )

            results.append(answer)

        # ====================================================
        # GOOGLE AI OVERVIEW
        # ====================================================

        ai_overview = data.get(
            "ai_overview"
        )

        if ai_overview:

            ai_text = None

            if isinstance(
                ai_overview,
                dict
            ):

                ai_text = (
                    ai_overview.get(
                        "markdown"
                    )
                    or
                    ai_overview.get(
                        "text"
                    )
                    or
                    ai_overview.get(
                        "content"
                    )
                )

            elif isinstance(
                ai_overview,
                str
            ):

                ai_text = ai_overview

            if ai_text:

                results.append(
                    {
                        "type":
                            "ai_overview",

                        "text":
                            ai_text,
                    }
                )

        # ====================================================
        # ORGANIC GOOGLE RESULTS
        # ====================================================

        organic_results = data.get(
            "organic_results",
            []
        )

        for item in organic_results[:10]:

            results.append(
                {
                    "type":
                        "organic_result",

                    "position":
                        item.get(
                            "position"
                        ),

                    "title":
                        item.get(
                            "title"
                        ),

                    "link":
                        item.get(
                            "link"
                        ),

                    "snippet":
                        item.get(
                            "snippet"
                        ),

                    "source":
                        item.get(
                            "source"
                        ),
                }
            )

        # ====================================================
        # NEWS RESULTS
        # ====================================================

        news_results = data.get(
            "news_results",
            []
        )

        for item in news_results[:5]:

            results.append(
                {
                    "type":
                        "news_result",

                    "title":
                        item.get(
                            "title"
                        ),

                    "link":
                        item.get(
                            "link"
                        ),

                    "snippet":
                        item.get(
                            "snippet"
                        ),

                    "source":
                        item.get(
                            "source"
                        ),

                    "date":
                        item.get(
                            "date"
                        ),
                }
            )

        # ====================================================
        # IF NOTHING FOUND
        # ====================================================

        if not results:

            return (
                f"SearchApi returned no useful "
                f"results for: {query}"
            )

        return json.dumps(
            results,
            ensure_ascii=False,
            indent=2
        )

    except requests.HTTPError as exc:

        try:
            error_body = response.text[:2000]
        except Exception:
            error_body = ""

        return (
            "SearchApi HTTP error: "
            f"{exc}\n"
            f"Response: {error_body}"
        )

    except requests.RequestException as exc:

        return (
            "SearchApi request failed: "
            f"{exc}"
        )

    except Exception as exc:

        return (
            "Google search failed: "
            f"{exc}"
        )


# ============================================================
# WIKIPEDIA
# ============================================================

@tool
def wikipedia_search(query: str) -> str:
    """
    Search Wikipedia for factual and historical information.

    Use this for:
    - people
    - historical events
    - scientific concepts
    - places
    - organizations
    - technologies
    - general factual background
    """

    try:

        search_results = wikipedia.search(
            query,
            results=5
        )

        if not search_results:

            return (
                f"No Wikipedia results found "
                f"for: {query}"
            )

        output = []

        for title in search_results[:3]:

            try:

                page = wikipedia.page(
                    title,
                    auto_suggest=False
                )

                summary = wikipedia.summary(
                    title,
                    sentences=5,
                    auto_suggest=False
                )

                output.append(
                    f"Title: {page.title}\n"
                    f"URL: {page.url}\n"
                    f"Summary:\n{summary}"
                )

            except (
                wikipedia.exceptions.DisambiguationError
            ) as exc:

                # Try the first few disambiguation options.
                options = exc.options[:3]

                output.append(
                    f"Multiple Wikipedia pages "
                    f"matched '{title}'. "
                    f"Possible matches: "
                    f"{', '.join(options)}"
                )

            except (
                wikipedia.exceptions.PageError
            ):

                continue

            except Exception:

                continue

        if not output:

            return (
                f"Wikipedia could not retrieve "
                f"content for: {query}"
            )

        return "\n\n---\n\n".join(
            output
        )

    except Exception as exc:

        return (
            "Wikipedia search failed: "
            f"{exc}"
        )


# ============================================================
# SAFE CALCULATOR
# ============================================================

_ALLOWED_OPERATORS = {

    ast.Add:
        operator.add,

    ast.Sub:
        operator.sub,

    ast.Mult:
        operator.mul,

    ast.Div:
        operator.truediv,

    ast.FloorDiv:
        operator.floordiv,

    ast.Mod:
        operator.mod,

    ast.Pow:
        operator.pow,

    ast.USub:
        operator.neg,

    ast.UAdd:
        operator.pos,
}


_ALLOWED_FUNCTIONS = {

    "sqrt":
        math.sqrt,

    "sin":
        math.sin,

    "cos":
        math.cos,

    "tan":
        math.tan,

    "asin":
        math.asin,

    "acos":
        math.acos,

    "atan":
        math.atan,

    "log":
        math.log,

    "log10":
        math.log10,

    "exp":
        math.exp,

    "ceil":
        math.ceil,

    "floor":
        math.floor,

    "fabs":
        math.fabs,

    "factorial":
        math.factorial,

    "pi":
        math.pi,

    "e":
        math.e,
}


def _safe_math(node):

    # --------------------------------------------------------
    # Number
    # --------------------------------------------------------

    if isinstance(
        node,
        ast.Constant
    ):

        if isinstance(
            node.value,
            (int, float)
        ):

            return node.value

        raise ValueError(
            "Only numbers are allowed."
        )

    # --------------------------------------------------------
    # Unary operation
    # --------------------------------------------------------

    if isinstance(
        node,
        ast.UnaryOp
    ):

        operator_type = type(
            node.op
        )

        if operator_type not in _ALLOWED_OPERATORS:

            raise ValueError(
                "Unsupported unary operator."
            )

        operand = _safe_math(
            node.operand
        )

        return _ALLOWED_OPERATORS[
            operator_type
        ](
            operand
        )

    # --------------------------------------------------------
    # Binary operation
    # --------------------------------------------------------

    if isinstance(
        node,
        ast.BinOp
    ):

        operator_type = type(
            node.op
        )

        if operator_type not in _ALLOWED_OPERATORS:

            raise ValueError(
                "Unsupported mathematical operator."
            )

        left = _safe_math(
            node.left
        )

        right = _safe_math(
            node.right
        )

        # Prevent enormous exponent calculations.
        if (
            operator_type is ast.Pow
            and abs(right) > 100
        ):

            raise ValueError(
                "Exponent is too large."
            )

        result = _ALLOWED_OPERATORS[
            operator_type
        ](
            left,
            right
        )

        # Prevent infinite results.
        if isinstance(
            result,
            float
        ):

            if not math.isfinite(
                result
            ):

                raise ValueError(
                    "Result is not finite."
                )

        return result

    # --------------------------------------------------------
    # Function call
    # --------------------------------------------------------

    if isinstance(
        node,
        ast.Call
    ):

        if not isinstance(
            node.func,
            ast.Name
        ):

            raise ValueError(
                "Unsupported function."
            )

        function_name = (
            node.func.id
        )

        if (
            function_name
            not in _ALLOWED_FUNCTIONS
        ):

            raise ValueError(
                f"Function '{function_name}' "
                "is not allowed."
            )

        function = _ALLOWED_FUNCTIONS[
            function_name
        ]

        arguments = [
            _safe_math(argument)
            for argument in node.args
        ]

        return function(
            *arguments
        )

    # --------------------------------------------------------
    # Constants such as pi/e
    # --------------------------------------------------------

    if isinstance(
        node,
        ast.Name
    ):

        if node.id in _ALLOWED_FUNCTIONS:

            value = _ALLOWED_FUNCTIONS[
                node.id
            ]

            if isinstance(
                value,
                (int, float)
            ):

                return value

        raise ValueError(
            f"Unknown variable: {node.id}"
        )

    # --------------------------------------------------------
    # Everything else
    # --------------------------------------------------------

    raise ValueError(
        "Unsupported mathematical expression."
    )


@tool
def calculator(expression: str) -> str:
    """
    Calculate mathematical expressions safely.

    Examples:

    25 * 40

    938472 * 382

    1000 / 12

    2 ** 10

    sqrt(144)

    sin(pi / 2)

    factorial(10)

    Use this tool whenever an accurate numerical
    calculation is required.
    """

    try:

        expression = (
            expression
            .strip()
        )

        if not expression:

            return (
                "No mathematical "
                "expression provided."
            )

        tree = ast.parse(
            expression,
            mode="eval"
        )

        result = _safe_math(
            tree.body
        )

        return str(
            result
        )

    except Exception as exc:

        return (
            "Calculation error: "
            f"{str(exc)}"
        )


# ============================================================
# TOOLS
# ============================================================

TOOLS = [
    google_search,
    wikipedia_search,
    calculator,
]


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are Spark AI, a highly capable AI assistant.

You have access to three external tools:

------------------------------------------------------------
1. GOOGLE SEARCH
------------------------------------------------------------

Tool name:
google_search

This uses SearchApi.io to search Google.

Use Google Search whenever the user asks about information
that can change over time.

Examples:

- latest news
- today's news
- current events
- current stock prices
- current cryptocurrency prices
- current product prices
- current weather
- recent AI developments
- recent technology releases
- current software versions
- recent company announcements
- current company information
- current sports information
- current websites
- information from the internet

If the user uses words such as:

"latest"
"today"
"current"
"now"
"recent"
"this week"
"this month"
"2026"
"right now"

you should strongly consider using Google Search.

Do not pretend your internal knowledge is current.

------------------------------------------------------------
2. WIKIPEDIA
------------------------------------------------------------

Tool name:
wikipedia_search

Use Wikipedia for factual and historical information.

Examples:

- biographies
- historical events
- scientific concepts
- technologies
- places
- organizations
- famous people
- general background information

Wikipedia is especially useful when the user asks about
a subject that does not require current information.

------------------------------------------------------------
3. CALCULATOR
------------------------------------------------------------

Tool name:
calculator

Use the calculator for mathematical calculations.

Examples:

- arithmetic
- percentages
- powers
- square roots
- trigonometry
- logarithms
- factorials
- financial calculations

Do not manually calculate complicated expressions when
the calculator tool is available.

------------------------------------------------------------
TOOL SELECTION
------------------------------------------------------------

You decide whether a tool is necessary.

Do not use tools unnecessarily.

Examples:

User:
"What is polymorphism in Java?"

→ Answer directly.

User:
"What is the latest Java version?"

→ Use Google Search.

User:
"Who was Albert Einstein?"

→ Wikipedia can be used.

User:
"What is 938472 * 382?"

→ Use calculator.

User:
"What is the current NVIDIA stock price?"

→ Use Google Search.

------------------------------------------------------------
SEARCH QUALITY
------------------------------------------------------------

When using Google Search:

1. Construct a precise search query.
2. Prefer authoritative sources when possible.
3. Consider multiple search results.
4. Do not blindly trust a single result.
5. Give the user a concise synthesized answer.
6. Include relevant source URLs when useful.
7. Never claim that you searched the web if you did not.

------------------------------------------------------------
ACCURACY
------------------------------------------------------------

Never invent search results.

If a tool fails, tell the user that the external lookup
failed rather than making up information.

If search results conflict, explain the conflict.

When answering from current web information, distinguish
between facts found in search results and your own reasoning.

------------------------------------------------------------
RESPONSE STYLE
------------------------------------------------------------

Answer directly.

Do not unnecessarily mention internal tools.

Do not say:

"I am an AI and I cannot..."

unless genuinely necessary.

Use clear formatting.

For technical questions, provide practical examples.

For calculations, give the result and a concise explanation
when appropriate.
"""


# ============================================================
# CREATE LANGCHAIN LLM
# ============================================================

def create_llm(model):
    """
    Create a LangChain ChatOpenAI instance using the
    OpenAI-compatible model configuration stored in MongoDB.

    Expected model dictionary:

    {
        "model": "...",
        "api_key": "...",
        "base_url": "https://..."
    }
    """

    base_url = (
        model["base_url"]
        .strip()
        .rstrip("/")
    )

    # --------------------------------------------------------
    # Normalize /chat/completions
    # --------------------------------------------------------

    endpoint_suffix = (
        "/chat/completions"
    )

    if base_url.endswith(
        endpoint_suffix
    ):

        base_url = base_url[
            :-len(endpoint_suffix)
        ]


    # --------------------------------------------------------
    # Create model
    # --------------------------------------------------------

    llm = ChatOpenAI(

        model=model[
            "model"
        ],

        api_key=model[
            "api_key"
        ],

        base_url=base_url,

        temperature=0.7,

        timeout=600,

        max_retries=2,
    )


    return llm


# ============================================================
# CREATE AGENT
# ============================================================

def create_agent_for_model(model):
    """
    Create a LangChain agent using the selected model.

    The model receives access to:

    - Google Search
    - Wikipedia
    - Calculator
    """

    llm = create_llm(
        model
    )

    agent = create_agent(

        model=llm,

        tools=TOOLS,

        system_prompt=SYSTEM_PROMPT,
    )

    return agent