# Configuration file for the Sphinx documentation builder.
# https://www.sphinx-doc.org/en/master/usage/configuration.html

project = "dftracer-workloads"
author = "Ray Andrew"
copyright = "2026, dftracer-workloads contributors"
release = "0.0.1"

# -- General configuration ---------------------------------------------------
extensions = [
    "myst_parser",
    "sphinx_copybutton",
    "sphinx_design",
]

myst_enable_extensions = [
    "colon_fence",  # ::: fenced directives
    "deflist",  # definition lists
    "attrs_inline",
    "substitution",
]
myst_heading_anchors = 3  # auto anchors for ##/### headings

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = []

# -- HTML output -------------------------------------------------------------
html_theme = "furo"
html_title = "dftracer-workloads"
html_theme_options = {
    "source_repository": "https://github.com/LLNL/dftracer-workloads",
    "source_branch": "main",
    "source_directory": "docs/source/",
}

# copybutton: strip shell prompts so pasted commands are clean
copybutton_prompt_text = r"\$ "
copybutton_prompt_is_regexp = True
