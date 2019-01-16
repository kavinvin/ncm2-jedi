# -*- coding: utf-8 -*-

from __future__ import absolute_import
import vim
from ncm2 import Ncm2Source, getLogger
import re
import jedi
# import os
from itertools import zip_longest


logger = getLogger(__name__)

import_pat = re.compile(r'^\s*(from|import)')
callsig_pat = re.compile(r'^\s*(?!from|import).*?[(,]\s*$')

class Source(Ncm2Source):

    def on_complete(self, ctx, lines):
        path = ctx['filepath']
        typed = ctx['typed']
        lnum = ctx['lnum']
        startccol = ctx['startccol']
        # ccol = ctx['ccol']

        # jedi doesn't work on comment
        # https://github.com/roxma/nvim-completion-manager/issues/62
        if typed.find('#') != -1:
            return

        src = "\n".join(lines)
        src = self.get_src(src, ctx)
        if not src.strip():
            # empty src may possibly block jedi execution, don't know why
            logger.info('ignore empty src [%s]', src)
            return

        logger.info('context [%s]', ctx)

        script = jedi.Script(src, lnum, len(typed), path)
        completions = script.completions()

        if callsig_pat.search(typed):
            try:
                signatures = script.call_signatures()
                cmdline_call_signatures(signatures)
            except Exception as ex:
                logger.info("")
        else:
            vim_command('echo ""')

        logger.info('completions %s', completions)

        matches = []

        for complete in completions:

            insert = complete.complete

            item = dict(word=ctx['base'] + insert,
                        icase=1,
                        dup=1,
                        menu="",
                        info="")

            item = self.match_formalize(ctx, item)

            # Fix the user typed case
            if item['word'].lower() == complete.name.lower():
                item['word'] = complete.name

            # snippet support
            # try:
            #     if (complete.type == 'function' or complete.type == 'class'):
            #         self.render_snippet(item, complete, is_import)
            # except Exception as ex:
            #     logger.exception(
            #         "exception parsing snippet for item: %s, complete: %s", item, complete)

            matches.append(item)

        logger.info('matches %s', matches)
        # workaround upstream issue by letting refresh=True. #116
        self.complete(ctx, startccol, matches)

    def render_snippet(self, item, complete, is_import):
        doc = complete.docstring()

        # This line has performance issue
        # https://github.com/roxma/nvim-completion-manager/issues/126
        # params = complete.params

        fundef = doc.split("\n")[0]

        params = re.search(r'(?:_method|' + re.escape(complete.name) + ')' + r'\((.*)\)', fundef)

        if params:
            item['menu'] = fundef

        logger.debug("building snippet [%s] type[%s] doc [%s]", item['word'], complete.type, doc)

        if params and not is_import:

            num = 1
            placeholders = []
            snip_args = ''

            params = params.group(1)
            if params != '':
                params = params.split(',')
                cnt = 0
                for param in params:
                    cnt += 1
                    if "=" in param or "*" in param or param[0] == '[':
                        break
                    else:
                        name = param.strip('[').strip(' ')

                        # Note: this is not accurate
                        if cnt == 1 and (name == 'self' or name == 'cls'):
                            continue

                        ph = self.snippet_placeholder(num, name)
                        placeholders.append(ph)
                        num += 1

                        # skip optional parameters
                        if "[" in param:
                            break

                snip_args = ', '.join(placeholders)
                if len(placeholders) == 0:
                    # don't jump out of parentheses if function has
                    # parameters
                    snip_args = self.snippet_placeholder(1)

            ph0 = self.snippet_placeholder(0)
            snippet = '%s(%s)%s' % (item['word'], snip_args, ph0)

            item['user_data']['is_snippet'] = 1
            item['user_data']['snippet'] = snippet
            logger.debug('snippet: [%s] placeholders: %s', snippet, placeholders)

    def snippet_placeholder(self, num, txt=''):
        txt = txt.replace('\\', '\\\\')
        txt = txt.replace('$', r'\$')
        txt = txt.replace('}', r'\}')
        if txt == '':
            return '${%s}' % num
        return '${%s:%s}' % (num, txt)

class VimError(Exception):
    def __init__(self, message, throwpoint, executing):
        super(type(self), self).__init__(message)
        self.message = message
        self.throwpoint = throwpoint
        self.executing = executing

    def __str__(self):
        return self.message + '; created by: ' + repr(self.executing)

def _catch_exception(string, is_eval):
    """
    Interface between vim and python calls back to it.
    Necessary, because the exact error message is not given by `vim.error`.
    """
    result = vim.eval('ncm2_jedi#_vim_exceptions({0}, {1})'.format(
        repr(PythonToVimStr(string, 'UTF-8')), int(is_eval)))
    if 'exception' in result:
        raise VimError(result['exception'], result['throwpoint'], string)
    return result['result']

def vim_command(string):
    _catch_exception(string, is_eval=False)


def vim_eval(string):
    return _catch_exception(string, is_eval=True)
import sys

is_py3 = sys.version_info[0] >= 3
if is_py3:
    ELLIPSIS = "…"
    unicode = str
else:
    ELLIPSIS = u"…"

try:
    # Somehow sys.prefix is set in combination with VIM and virtualenvs.
    # However the sys path is not affected. Just reset it to the normal value.
    sys.prefix = sys.base_prefix
    sys.exec_prefix = sys.base_exec_prefix
except AttributeError:
    # If we're not in a virtualenv we don't care. Everything is fine.
    pass


class PythonToVimStr(unicode):
    """ Vim has a different string implementation of single quotes """
    __slots__ = []

    def __new__(cls, obj, encoding='UTF-8'):
        if not (is_py3 or isinstance(obj, unicode)):
            obj = unicode.__new__(cls, obj, encoding)

        # Vim cannot deal with zero bytes:
        obj = obj.replace('\0', '\\0')
        return unicode.__new__(cls, obj)

    def __repr__(self):
        # this is totally stupid and makes no sense but vim/python unicode
        # support is pretty bad. don't ask how I came up with this... It just
        # works...
        # It seems to be related to that bug: http://bugs.python.org/issue5876
        if unicode is str:
            s = self
        else:
            s = self.encode('UTF-8')
        return '"%s"' % s.replace('\\', '\\\\').replace('"', r'\"')

#
# cmdline call signatures
#
def cmdline_call_signatures(signatures):
    def get_params(s):
        return [p.description.replace('\n', '').replace('param ', '', 1) for p in s.params]

    def escape(string):
        return string.replace('"', '\\"').replace(r'\n', r'\\n')

    def join():
        return ', '.join(filter(None, (left, center, right)))

    def too_long():
        return len(join()) > max_msg_len

    if len(signatures) > 1:
        params = zip_longest(*map(get_params, signatures), fillvalue='_')
        params = ['(' + ', '.join(p) + ')' for p in params]
    else:
        params = get_params(signatures[0])

    index = next(iter(s.index for s in signatures if s.index is not None), None)

    # Allow 12 characters for showcmd plus 18 for ruler - setting
    # noruler/noshowcmd here causes incorrect undo history
    max_msg_len = int(vim_eval('&columns')) - 12
    if int(vim_eval('&ruler')):
        max_msg_len -= 18
    max_msg_len -= len(signatures[0].name) + 2  # call name + parentheses

    if max_msg_len < (1 if params else 0):
        return
    elif index is None:
        text = escape(', '.join(params))
        if params and len(text) > max_msg_len:
            text = ELLIPSIS
    elif max_msg_len < len(ELLIPSIS):
        return
    else:
        left = escape(', '.join(params[:index]))
        center = escape(params[index])
        right = escape(', '.join(params[index + 1:]))
        while too_long():
            if left and left != ELLIPSIS:
                left = ELLIPSIS
                continue
            if right and right != ELLIPSIS:
                right = ELLIPSIS
                continue
            if (left or right) and center != ELLIPSIS:
                left = right = None
                center = ELLIPSIS
                continue
            if too_long():
                # Should never reach here
                return

    max_num_spaces = max_msg_len
    if index is not None:
        max_num_spaces -= len(join())
    _, column = signatures[0].bracket_start
    # spaces = min(int(vim_eval('g:ncm2_jedi#first_col +'
    #                           'wincol() - col(".")')) +
    #              column - len(signatures[0].name),
    #              max_num_spaces) * ' '
    spaces = ""

    if index is not None:
        vim_command('                      echon "%s" | '
                    'echohl Function     | echon "%s" | '
                    'echohl None         | echon "("  | '
                    'echohl jediFunction | echon "%s" | '
                    'echohl jediFat      | echon "%s" | '
                    'echohl jediFunction | echon "%s" | '
                    'echohl None         | echon ")"'
                    % (spaces, signatures[0].name,
                       left + ', ' if left else '',
                       center, ', ' + right if right else ''))
    else:
        vim_command('                      echon "%s" | '
                    'echohl Function     | echon "%s" | '
                    'echohl None         | echon "(%s)"'
                    % (spaces, signatures[0].name, text))

try:
    # set RLIMIT_DATA
    # https://github.com/roxma/nvim-completion-manager/issues/62
    import resource
    import psutil
    mem = psutil.virtual_memory()
    resource.setrlimit(resource.RLIMIT_DATA,
                       (mem.total / 3, resource.RLIM_INFINITY))
except Exception as ex:
    logger.exception('set RLIMIT_DATA failed')

source = Source(vim)

on_complete = source.on_complete
