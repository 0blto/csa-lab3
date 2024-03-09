section data
    word: 'Hello, '

section text
start:
    mov @r2 0
    printer:
        ld @r1 (word|r2)
        cmp @r1 0
        jz :read_char
        st !stdout @r1
        inc @r2
        jmp :printer

    read_char:
        ld @r5 !stdin
        cmp @r5 0
        jz :fin
        st !stdout @r5
        jmp :read_char
    fin:
        hlt