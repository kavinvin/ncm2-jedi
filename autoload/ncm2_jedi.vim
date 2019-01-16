if get(s:, 'loaded', 0)
    finish
endif
let s:loaded = 1

let g:ncm2_jedi#python_version = get(g:,
            \ 'ncm2_jedi#python_version',
            \ 3)

if g:ncm2_jedi#python_version != 2
    let g:ncm2_jedi#proc = yarp#py3('ncm2_jedi')
else
    " FIXME python2 has wired error message, but it is still usable, I
    " don't know what's wrong
    let g:ncm2_jedi#proc = yarp#py('ncm2_jedi')
endif

let g:ncm2_jedi#source = extend(get(g:, 'ncm2_jedi#source', {}), {
            \ 'name': 'jedi',
            \ 'ready': 0,
            \ 'priority': 8,
            \ 'mark': 'py',
            \ 'scope': ['python'],
            \ 'subscope_enable': 1,
            \ 'complete_pattern': [
            \       '^\s*(import|from).*\s',
            \       '\.',
            \       '\(\s?',
            \       ',\s?'],
            \ 'on_complete': 'ncm2_jedi#on_complete',
            \ 'on_warmup': 'ncm2_jedi#on_warmup',
            \ }, 'keep')

let g:ncm2_jedi#proc.on_load = {-> ncm2#set_ready(g:ncm2_jedi#source)}

func! ncm2_jedi#init()
    call ncm2#register_source(g:ncm2_jedi#source)
endfunc

func! ncm2_jedi#on_warmup(ctx)
    call g:ncm2_jedi#proc.jobstart()
endfunc

func! ncm2_jedi#on_complete(ctx)
    call g:ncm2_jedi#proc.try_notify('on_complete', a:ctx, getline(1, '$'))
endfunc

" Helper function instead of `python vim.eval()`, and `.command()` because
" these also return error definitions.
func! ncm2_jedi#_vim_exceptions(str, is_eval)
    let l:result = {}
    try
        if a:is_eval
            let l:result.result = eval(a:str)
        else
            execute a:str
            let l:result.result = ''
        endif
    catch
        let l:result.exception = v:exception
        let l:result.throwpoint = v:throwpoint
    endtry
    return l:result
endfunc

" +conceal is the default for vim >= 7.3
let s:e = "'?!?'" " g:jedi#call_signature_escape
let s:full = s:e.'jedi=.\{-}'.s:e.'.\{-}'.s:e.'jedi'.s:e
let s:ignore = s:e.'jedi.\{-}'.s:e
exe 'syn match jediIgnore "'.s:ignore.'" contained conceal'
setlocal conceallevel=2
syn match jediFatSymbol "\*_\*" contained conceal
syn match jediFat "\*_\*.\{-}\*_\*" contained contains=jediFatSymbol
syn match jediSpace "\v[ ]+( )@=" contained
exe 'syn match jediFunction "'.s:full.'" keepend extend '
            \ .' contains=jediIgnore,jediFat,jediSpace'
            \ .' containedin=pythonComment,pythonString,pythonRawString'
unlet! s:e s:full s:ignore

hi def link jediIgnore Ignore
hi def link jediFatSymbol Ignore
hi def link jediSpace Normal

if exists('g:colors_name')
    hi def link jediFunction CursorLine
    hi def link jediFat TabLine
else
    hi def jediFunction term=NONE cterm=NONE ctermfg=6 guifg=Black gui=NONE ctermbg=0 guibg=Grey
    hi def jediFat term=bold,underline cterm=bold,underline gui=bold,underline ctermbg=0 guibg=#555555
endif

hi def jediUsage cterm=reverse gui=standout
