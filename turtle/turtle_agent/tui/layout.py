from prompt_toolkit.layout.containers import HSplit, Window, to_container
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import TextArea, Frame
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.formatted_text import HTML, ANSI
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.data_structures import Point
from rich.console import Console
from rich.markdown import Markdown
import io
import shutil

class ModelPickerControl(FormattedTextControl):
    def __init__(self, models: list[str], current_model: str = ""):
        self.models = models
        self.selected_idx = 0
        if current_model in models:
            self.selected_idx = models.index(current_model)
        super().__init__(text=self._render, focusable=True)

    def _render(self):
        tokens = [("class:title", "▸ Select Model (Use ↑/↓ arrows, Enter to select, Esc to cancel):\n\n")]
        for i, m in enumerate(self.models):
            if i == self.selected_idx:
                tokens.append(("class:prompt", f"  ❯ {m}\n"))
            else:
                tokens.append(("class:title", f"    {m}\n"))
        return tokens

    def move_up(self):
        self.selected_idx = max(0, self.selected_idx - 1)

    def move_down(self):
        self.selected_idx = min(len(self.models) - 1, self.selected_idx + 1)

    def get_selected(self) -> str:
        if self.models:
            return self.models[self.selected_idx]
        return ""

class TurtleLayout:
    def __init__(self):
        self._transcript_chunks = [(False, "[#a9b1d6]▸[/] [#7aa2f7]Turtle Engine[/]\n  [#565f89]└─[/] [#9ece6a]System healthy[/]\n")]
        
        self.completer = WordCompleter([
            '/help', '/tree', '/checkout', '/undo', '/models', 
            '/model', '/clear', '/compact', '/exit', '/quit'
        ], ignore_case=True)
        
        term_width = max(80, min(shutil.get_terminal_size((120, 24)).columns, 240))
        self.console = Console(file=io.StringIO(), force_terminal=True, color_system="truecolor", width=term_width - 4)
        self._rendered_lines = 1
        
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
        
        self.input_area = TextArea(
            height=Dimension(min=3, max=10),
            prompt=HTML("<prompt>▸ </prompt>"),
            multiline=True,
            wrap_lines=True,
            scrollbar=True,
            completer=self.completer,
            complete_while_typing=True,
        )
        
        self.input_frame = Frame(
            body=self.input_area,
            style="class:input-frame"
        )
        
        self.bottom_container = HSplit([self.input_frame])
        
        self.footer_text = FormattedTextControl(text=HTML(" NORMAL | <style fg='#7aa2f7'>main</style> | <style fg='#565f89'>Disconnected</style>"))
        self.footer_window = Window(
            content=self.footer_text,
            height=Dimension.exact(1),
            style="class:status-toolbar"
        )
        
        self.container = HSplit([
            Frame(
                body=self.transcript_area,
                title=HTML("<title> Turtle Session </title>"),
                style="class:transcript-frame"
            ),
            self.bottom_container,
            self.footer_window
        ])
        
        self.picker_control = None

    def show_model_picker(self, models: list[str], current_model: str = ""):
        self.picker_control = ModelPickerControl(models, current_model)
        h = max(min(len(models) + 3, 14), 5)
        picker_window = Window(content=self.picker_control, height=Dimension(min=h, max=h))
        picker_frame = Frame(body=picker_window, title=HTML("<title> Model Selector </title>"), style="class:input-frame")
        self.bottom_container.children = [to_container(picker_frame)]

    def hide_model_picker(self):
        self.picker_control = None
        self.bottom_container.children = [to_container(self.input_frame)]

    def _get_rendered_ansi(self):
        self.console.file = io.StringIO()
        
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
        
        if len(self._transcript_chunks) > 2000:
            self._transcript_chunks = self._transcript_chunks[-2000:]
            
        ansi_str = self._get_rendered_ansi()
        self._rendered_lines = ansi_str.count('\n')
        self.transcript_control.text = ANSI(ansi_str)
        
    def update_footer(self, text: str):
        self.footer_text.text = HTML(f" {text}")
        
    def update_completer(self, models: list):
        commands = [
            '/help', '/tree', '/checkout', '/undo', '/models', 
            '/model', '/clear', '/compact', '/exit', '/quit'
        ]
        model_commands = [f"/model {m}" for m in models]
        self.completer.words = commands + model_commands
