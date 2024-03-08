section data
section text
start:
    read_char:
        ld @r5 !stdin
        cmp @r5 0
        jz :fin
        st !stdout @r5
        jmp :read_char
    fin:
        hlt