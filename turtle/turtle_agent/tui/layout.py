from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea, Frame
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.formatted_text import HTML, ANSI
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.data_structures import Point
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text
import io
import re

class TurtleLayout:
    def __init__(self):
        self._transcript_chunks = [(False, "[bold green]Welcome to Turtle TUI![/bold green]")]
        
        self.completer = WordCompleter([
            '/help', '/tree', '/checkout', '/undo', '/models', 
            '/model', '/clear', '/compact', '/exit', '/quit'
        ], ignore_case=True)
        
        self.console = Console(file=io.StringIO(), force_terminal=True, color_system="truecolor", width=120)
        self._rendered_lines = 1
        
        # 1. Transcript Area (Read-only history)
        self.transcript_control = FormattedTextControl(
            text=ANSI(self._get_rendered_ansi()),
            focusable=True
        )
        self.transcript_control.get_cursor_position = self._get_cursor_position
        
        self.transcript_area = Window(
            content=self.transcript_control,
            wrap_lines=True,
            always_hide_cursor=True,
            scroll_offsets=None
        )
        
        # 2. Input Area
        self.input_area = TextArea(
            height=Dimension(min=3, max=10),
            prompt="turtle> ",
            multiline=True,
            wrap_lines=True,
            scrollbar=True,
            completer=self.completer,
            complete_while_typing=True,
        )
        
        # 3. Footer
        self.footer_text = FormattedTextControl(text=HTML("<b>Turtle</b> | Use <style bg='ansiyellow' fg='ansiblack'>Alt+Enter</style> for newline, <style bg='ansiyellow' fg='ansiblack'>Enter</style> to submit, <style bg='ansiyellow' fg='ansiblack'>Ctrl+C</style> to exit"))
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

    def _get_rendered_ansi(self):
        self.console.file.truncate(0)
        self.console.file.seek(0)
        
        for is_md, chunk in self._transcript_chunks:
            if is_md:
                self.console.print(Markdown(chunk))
            else:
                self.console.print(chunk)
                
        return self.console.file.getvalue()

    def _get_cursor_position(self):
        return Point(0, self._rendered_lines)

    def append_transcript(self, text: str, is_markdown: bool = False):
        self._transcript_chunks.append((is_markdown, text))
        
        # Prevent unbounded memory growth
        if len(self._transcript_chunks) > 2000:
            self._transcript_chunks = self._transcript_chunks[-2000:]
            
        ansi_str = self._get_rendered_ansi()
        self._rendered_lines = ansi_str.count('\n')
        self.transcript_control.text = ANSI(ansi_str)
        
    def update_footer(self, text: str):
        self.footer_text.text = HTML(text)
        
    def update_completer(self, models: list):
        commands = [
            '/help', '/tree', '/checkout', '/undo', '/models', 
            '/model', '/clear', '/compact', '/exit', '/quit'
        ]
        model_commands = [f"/model {m}" for m in models]
        self.completer.words = commands + model_commands
