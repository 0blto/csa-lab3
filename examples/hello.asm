section data
    word: 'Hello world!'

section text
start:
    mov @r2 0
    printer:
        ld @r1 (word|r2)
        cmp @r1 0
        jz :fin
        st !stdout @r1
        inc @r2
        jmp :printer
    fin:
        hlt