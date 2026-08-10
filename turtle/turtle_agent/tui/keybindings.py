from prompt_toolkit.key_binding import KeyBindings
import time

def create_keybindings(submit_callback, exit_callback, interrupt_callback, picker_select_callback=None, picker_cancel_callback=None, layout_engine=None):
    kb = KeyBindings()
    
    last_interrupt_time = 0

    @kb.add('c-c')
    def _(event):
        nonlocal last_interrupt_time
        if layout_engine and layout_engine.picker_control and event.app.layout.has_focus(layout_engine.picker_control):
            if picker_cancel_callback:
                picker_cancel_callback()
            return

        if event.current_buffer and event.current_buffer.text:
            event.current_buffer.text = ''
            return
            
        now = time.time()
        if now - last_interrupt_time < 1.0:
            exit_callback()
        else:
            last_interrupt_time = now
            if interrupt_callback:
                interrupt_callback()

    @kb.add('up')
    @kb.add('k')
    def _(event):
        if layout_engine and layout_engine.picker_control and event.app.layout.has_focus(layout_engine.picker_control):
            layout_engine.picker_control.move_up()
            event.app.invalidate()

    @kb.add('down')
    @kb.add('j')
    def _(event):
        if layout_engine and layout_engine.picker_control and event.app.layout.has_focus(layout_engine.picker_control):
            layout_engine.picker_control.move_down()
            event.app.invalidate()

    @kb.add('escape')
    def _(event):
        if layout_engine and layout_engine.picker_control and event.app.layout.has_focus(layout_engine.picker_control):
            if picker_cancel_callback:
                picker_cancel_callback()
            return
        if interrupt_callback:
            interrupt_callback()

    @kb.add('enter')
    def _(event):
        if layout_engine and layout_engine.picker_control and event.app.layout.has_focus(layout_engine.picker_control):
            selected = layout_engine.picker_control.get_selected()
            if picker_select_callback:
                picker_select_callback(selected)
            return

        if event.current_buffer and event.current_buffer.text.strip():
            submit_callback(event.current_buffer.text)
            event.current_buffer.text = ''

    @kb.add('escape', 'enter')
    def _(event):
        if event.current_buffer:
            event.current_buffer.insert_text('\n')

    return kb
