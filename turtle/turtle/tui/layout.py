from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea, Frame
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.formatted_text import HTML
import re

class TurtleLayout:
    def __init__(self):
        # 1. Transcript Area (Read-only history)
        self.transcript_area = TextArea(
            text="Welcome to Turtle TUI!\n",
            read_only=True,
            scrollbar=True,
            line_numbers=False,
            wrap_lines=True,
        )
        
        # 2. Input Area
        self.input_area = TextArea(
            height=Dimension(min=3, max=10),
            prompt="turtle> ",
            multiline=True,
            wrap_lines=True,
            scrollbar=True,
        )
        
        # 3. Footer
        self.footer_text = FormattedTextControl(text=HTML("<b>Turtle</b> | Use <style bg='ansiyellow' fg='ansiblack'>Shift+Enter</style> for newline, <style bg='ansiyellow' fg='ansiblack'>Enter</style> to submit, <style bg='ansiyellow' fg='ansiblack'>Ctrl+C</style> to exit"))
        self.footer_window = Window(
            content=self.footer_text,
            height=Dimension.exact(1),
            style="class:status-toolbar"
        )
        
        # 4. Main Layout Container
        self.container = HSplit([
            self.transcript_area,
            Window(height=1, char='-', style="class:line"),
            self.input_area,
            self.footer_window
        ])

    def append_transcript(self, text: str):
        # Strip rich markup tags like [bold green] or [/bold]
        clean_text = re.sub(r'\[/?(?:bold|dim|cyan|yellow|red|green|blue|white)(?:\s+[^\]]+)?\]', '', text)
        self.transcript_area.text += clean_text + "\n"
        
    def update_footer(self, text: str):
        self.footer_text.text = HTML(text)
