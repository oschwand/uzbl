import re

# Map these functions/variables in the plugins namespace to the uzbl object.
__export__ = ['clear_keycmd', 'set_keycmd', 'set_cursor_pos', 'get_keylet']

# Regular expression compile cache.
_RE_CACHE = {}

# Hold the keylets.
UZBLS = {}

# Simple key names map.
_SIMPLEKEYS = {
  'Control': 'Ctrl',
  'ISO_Left_Tab': 'Shift-Tab',
  'space':'Space',
}

# Keycmd format which includes the markup for the cursor.
KEYCMD_FORMAT = "%s<span @cursor_style>%s</span>%s"


def escape(str):
    '''Prevent outgoing keycmd values from expanding inside the
    status_format.'''

    if not str:
        return ''

    for char in ['\\', '@']:
        if char in str:
            str = str.replace(char, '\\'+char)

    return "@[%s]@" % str


def get_regex(regex):
    '''Compiling regular expressions is a very time consuming so return a
    pre-compiled regex match object if possible.'''

    if regex not in _RE_CACHE:
        _RE_CACHE[regex] = re.compile(regex).match

    return _RE_CACHE[regex]


class Keylet(object):
    '''Small per-instance object that tracks all the keys held and characters
    typed.'''

    def __init__(self):
        self.cmd = ''
        self.cursor = 0
        self.held = []

        # to_string() string building cache.
        self._to_string = None

        self.modcmd = False
        self.wasmod = False

    def __repr__(self):
        return '<Keycmd(%r)>' % self.to_string()


    def to_string(self):
        '''Return a string representation of the keys held and pressed that
        have been recorded.'''

        if self._to_string is not None:
            # Return cached keycmd string.
            return self._to_string

        if not self.held:
            self._to_string = self.cmd

        else:
            self._to_string = ''.join(['<%s>' % key for key in self.held])
            if self.cmd:
                self._to_string += self.cmd

        return self._to_string


    def match(self, regex):
        '''See if the keycmd string matches the given regex.'''

        return bool(get_regex(regex)(self.to_string()))


def make_simple(key):
    '''Make some obscure names for some keys friendlier.'''

    # Remove left-right discrimination.
    if key.endswith('_L') or key.endswith('_R'):
        key = key[:-2]

    if key in _SIMPLEKEYS:
        key = _SIMPLEKEYS[key]

    return key


def add_instance(uzbl, *args):
    '''Create the Keylet object for this uzbl instance.'''

    UZBLS[uzbl] = Keylet()


def del_instance(uzbl, *args):
    '''Delete the Keylet object for this uzbl instance.'''

    if uzbl in UZBLS:
        del UZBLS[uzbl]


def get_keylet(uzbl):
    '''Return the corresponding keylet for this uzbl instance.'''

    # Startup events are not correctly captured and sent over the uzbl socket
    # yet so this line is needed because the INSTANCE_START event is lost.
    if uzbl not in UZBLS:
        add_instance(uzbl)

    keylet = UZBLS[uzbl]
    keylet._to_string = None
    return keylet


def clear_keycmd(uzbl):
    '''Clear the keycmd for this uzbl instance.'''

    k = get_keylet(uzbl)
    k.cmd = ''
    k.cursor = 0
    k._to_string = None

    if k.modcmd:
        k.wasmod = True

    k.modcmd = False
    config = uzbl.get_config()
    if 'keycmd' not in config or config['keycmd'] != '':
        config['keycmd'] = ''

    uzbl.event('KEYCMD_CLEAR')


def update_event(uzbl, k):
    '''Raise keycmd & modcmd update events.'''

    config = uzbl.get_config()
    if k.modcmd:
        keycmd = k.to_string()
        uzbl.event('MODCMD_UPDATE', k)
        if keycmd != k.to_string():
            return

        if 'modcmd_updates' in config and config['modcmd_updates'] != '1':
            return

        return uzbl.set('keycmd', escape(keycmd))

    if 'keycmd_events' in config and config['keycmd_events'] != '1':
        return

    keycmd = k.cmd
    uzbl.event('KEYCMD_UPDATE', k)
    if keycmd != k.cmd:
        return

    if not k.cmd:
        return uzbl.set('keycmd', '')

    # Generate the pango markup for the cursor in the keycmd.
    if k.cursor < len(k.cmd):
        cursor = k.cmd[k.cursor]

    else:
        cursor = ' '

    chunks = map(escape, [k.cmd[:k.cursor], cursor, k.cmd[k.cursor+1:]])
    uzbl.set('keycmd', KEYCMD_FORMAT % tuple(chunks))


def key_press(uzbl, key):
    '''Handle KEY_PRESS events. Things done by this function include:

    1. Ignore all shift key presses (shift can be detected by capital chars)
    2. Re-enable modcmd var if the user presses another key with at least one
       modkey still held from the previous modcmd (I.e. <Ctrl>+t, clear &
       <Ctrl>+o without having to re-press <Ctrl>)
    3. In non-modcmd mode:
         a. BackSpace deletes the character before the cursor position.
         b. Delete deletes the character at the cursor position.
         c. End moves the cursor to the end of the keycmd.
         d. Home moves the cursor to the beginning of the keycmd.
         e. Return raises a KEYCMD_EXEC event then clears the keycmd.
         f. Escape clears the keycmd.
    4. If keycmd and held keys are both empty/null and a modkey was pressed
       set modcmd mode.
    5. If in modcmd mode only mod keys are added to the held keys list.
    6. Keycmd is updated and events raised if anything is changed.'''

    if key.startswith('Shift_'):
        return

    if len(key) > 1:
        key = make_simple(key)

    k = get_keylet(uzbl)
    cmdmod = False
    if k.held and k.wasmod:
        k.modcmd = True
        k.wasmod = False
        cmdmod = True

    if k.cmd and key == 'Space':
        k.cmd = "%s %s" % (k.cmd[:k.cursor], k.cmd[k.cursor:])
        k.cursor += 1
        cmdmod = True

    elif not k.modcmd and k.cmd and key in ['BackSpace', 'Delete']:
        if key == 'BackSpace' and k.cursor > 0:
            k.cursor -= 1
            k.cmd = k.cmd[:k.cursor] + k.cmd[k.cursor+1:]

        elif key == 'Delete':
            cmd = k.cmd
            k.cmd = k.cmd[:k.cursor] + k.cmd[k.cursor+1:]
            if k.cmd != cmd:
                cmdmod = True

        if not k.cmd:
            clear_keycmd(uzbl)

        elif key == 'BackSpace':
            cmdmod = True

    elif not k.modcmd and key == 'Return':
        if k.cmd:
            uzbl.event('KEYCMD_EXEC', k)

        clear_keycmd(uzbl)

    elif not k.modcmd and key == 'Escape':
        clear_keycmd(uzbl)

    elif not k.modcmd and k.cmd and key == 'Left':
        if k.cursor > 0:
            k.cursor -= 1
            cmdmod = True

    elif not k.modcmd and k.cmd and key == 'Right':
        if k.cursor < len(k.cmd):
            k.cursor += 1
            cmdmod = True

    elif not k.modcmd and k.cmd and key == 'End':
        if k.cursor != len(k.cmd):
            k.cursor = len(k.cmd)
            cmdmod = True

    elif not k.modcmd and k.cmd and key == 'Home':
        if k.cursor:
            k.cursor = 0
            cmdmod = True

    elif not k.held and not k.cmd and len(key) > 1:
        k.modcmd = True
        k.held.append(key)
        cmdmod = True

    elif k.modcmd:
        cmdmod = True
        if len(key) > 1:
            if key == 'Shift-Tab' and 'Tab' in k.held:
                k.held.remove('Tab')

            if key not in k.held:
                k.held.append(key)
                k.held.sort()

        else:
            k.cmd = "%s%s%s" % (k.cmd[:k.cursor], key, k.cmd[k.cursor:])
            k.cursor += 1

    else:
        config = uzbl.get_config()
        if 'keycmd_events' not in config or config['keycmd_events'] == '1':
            if len(key) == 1:
                cmdmod = True
                k.cmd = "%s%s%s" % (k.cmd[:k.cursor], key, k.cmd[k.cursor:])
                k.cursor += 1

        elif k.cmd:
            cmdmod = True
            k.cmd = ''
            k.cursor = 0

    if cmdmod:
        update_event(uzbl, k)


def key_release(uzbl, key):
    '''Respond to KEY_RELEASE event. Things done by this function include:

    1. Remove the key from the keylet held list.
    2. If the key removed was a mod key and it was in a mod-command then
       raise a MODCMD_EXEC event then clear the keycmd.
    3. Stop trying to restore mod-command status with wasmod if both the
       keycmd and held list are empty/null.
    4. Update the keycmd uzbl variable if anything changed.'''

    if len(key) > 1:
        key = make_simple(key)

    k = get_keylet(uzbl)

    cmdmod = False
    if key in ['Shift', 'Tab'] and 'Shift-Tab' in k.held:
        key = 'Shift-Tab'

    elif key in ['Shift', 'Alt'] and 'Meta' in k.held:
        key = 'Meta'

    if key in k.held:
        if k.modcmd:
            uzbl.event('MODCMD_EXEC', k)

        k.held.remove(key)
        clear_keycmd(uzbl)

    if not k.held and not k.cmd and k.wasmod:
        k.wasmod = False

    if cmdmod:
       update_event(uzbl, k)


def set_keycmd(uzbl, keycmd):
    '''Allow setting of the keycmd externally.'''

    k = get_keylet(uzbl)
    k.wasmod = k.modcmd = False
    k._to_string = None
    k.cmd = keycmd
    k.cursor = len(keycmd)
    update_event(uzbl, k)


def set_cursor_pos(uzbl, index):
    '''Allow setting of the cursor position externally. Supports negative
    indexing.'''

    cursor = int(index.strip())
    k = get_keylet(uzbl)

    if cursor < 0:
        cursor = len(k.cmd) + cursor

    if cursor < 0:
        cursor = 0

    if cursor > len(k.cmd):
        cursor = len(k.cmd)

    k.cursor = cursor
    update_event(uzbl, k)


def init(uzbl):
    '''Connect handlers to uzbl events.'''

    connects = {'INSTANCE_START': add_instance,
      'INSTANCE_EXIT': del_instance,
      'KEY_PRESS': key_press,
      'KEY_RELEASE': key_release,
      'SET_KEYCMD': set_keycmd,
      'SET_CURSOR_POS': set_cursor_pos}

    uzbl.connect_dict(connects)
