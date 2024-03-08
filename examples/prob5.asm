section data
section text
    mov @r1 1
    mov @r2 1
    cycle:
        inc @r2
        cmp @r2 2
        jz :two
        cmp @r2 3
        jz :three
        cmp @r2 5
        jz :default
        cmp @r2 7
        jz :default
        cmp @r2 11
        jz :default
        cmp @r2 13
        jz :default
        cmp @r2 17
        jz :default
        cmp @r2 19
        jz :default
        cmp @r2 20
        jz :fin
        jmp :cycle
    connect:
        mul @r1 @r3
        jmp :cycle

    two:
        mov @r3 @r2
        mov @r4 4
        jmp :degree

    three:
        mov @r3 @r2
        mov @r4 2
        jmp :degree

    default:
        mov @r3 @r2
        jmp :connect

    degree:
        dec @r4
        jz :connect
        mul @r3 @r2
        jmp :degree

    fin:
        st !stdout @r1
        hlt