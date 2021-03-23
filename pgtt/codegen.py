"""
Copyright (c) 2019 Ash Wilding. All rights reserved.

SPDX-License-Identifier: MIT
"""

# Internal deps
from . import args
from . import log
from . import mmu
from . import table
from . import mmap
from .mmap import Region

def _mk_table( n:int, t:table.Table ) -> str:
    """
    Generate assembly to begin programming a translation table.

    args
    ====

        n
                    table number in sequential order from ttbr0_eln

        t
                    translation table being programmed
    """
    return f"""
program_table_{n}:
    MOV64   x8, {hex(t.addr)}          // base address of this table
    ADD     x8, x8, x6                 // add global base
    MOV64   x9, {hex(t.chunk)}         // chunk size"""

def _mk_blocks( n:int, t:table.Table, idx:int, r:Region ) -> str:
    """
    Generate assembly to program a range of contiguous block/page entries.

    args
    ====

        n
                    table number in sequential order from ttbr0_eln

        t
                    translation table being programmed

        idx
                    index of the first block/page in the contiguous range

        r
                    the memory region
    """
    if r.memory_type == mmap.MEMORY_TYPE.device:
        template_reg = "x2" if t.level < 3 else "x3"
    elif r.memory_type == mmap.MEMORY_TYPE.rw_data:
        template_reg = "x4" if t.level < 3 else "x5"
    else:
        template_reg = "x20" if t.level < 3 else "x21"

    return f"""program_table_{n}_entry_{idx}{f'_to_{idx + r.num_contig - 1}' if r.num_contig > 1 else ''}:

    MOV64   x10, {idx}                 // idx
    MOV64   x11, {r.num_contig}        // number of contiguous entries
    MOV64   x12, {hex(r.addr)}         // output address of entry[idx]
1:
    ORR     x12, x12, {template_reg}    // merge output address with template
    STR     X12, [x8, x10, lsl #3]      // write entry into table
    ADD     x10, x10, #1                // prepare for next entry idx+1
    ADD     x12, x12, x9                // add chunk to address
    SUBS    x11, x11, #1                // loop as required
    B.NE    1b
"""



def _mk_next_level_table( n:int, idx:int, next_t:table.Table ) -> str:
    """
    Generate assembly to program a pointer to a next level table.

    args
    ====

        n
                    parent table number in sequential order from ttbr0_eln

        idx
                    index of the next level table pointer

        next_t
                    the next level translation table
    """
    return f"""
program_table_{n}_entry_{idx}:
    MOV64   x10, {idx}                 // idx
    MOV64   x11, {hex(next_t.addr)}    // next-level table address
    ADD     x11, x11, x6               // add base address
    ORR     x11, x11, #0x3             // next-level table descriptor
    STR     x11, [x8, x10, lsl #3]     // write entry into table"""



def _mk_asm() -> str:
    """
    Generate assembly to program all allocated translation tables.
    """
    string = ""
    for n,t in enumerate(table.Table._allocated):
        string += _mk_table(n, t)
        keys = sorted(list(t.entries.keys()))
        while keys:
            idx = keys[0]
            entry = t.entries[idx]
            if type(entry) is Region:
                string += _mk_blocks(n, t, idx, entry)
                for k in range(idx, idx+entry.num_contig):
                    keys.remove(k)
            else:
                string += _mk_next_level_table(n, idx, entry)
                keys.remove(idx)
    return string

ttbr="ttbr0"
ttbro="ttbr1"
if args.ttbr1:
   ttbr="ttbr1"
   ttbro="ttbr0"

_newline = "\n"
_tmp =f"""/*
 * This file was automatically generated using arm64-pgtable-tool.
 * See: https://github.com/ashwio/arm64-pgtable-tool
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 *
 * This code programs the following translation table structure:
 *
{_newline.join([f' * {ln}' for ln in str(table.root).splitlines()])}
 *
 * The following command line arguments were passed to arm64-pgtable-tool:
 *
 *      -i {args.i}
 *      -ttb {args.ttb}
 *      -el {args.el}
 *      -tg {args.tg_str}
 *      -tsz {args.tsz}
 *
{_newline.join([f' * {ln}' for ln in table.Table.usage().splitlines()])}
 * It is the programmer's responsibility to guarantee this.
 *
 * The programmer must also ensure that the virtual memory region containing the
 * translation tables is itself marked as NORMAL in the memory map file.
 */
    .macro  MOV64 reg,value
    movz    \\reg,#\\value & 0xffff
    .if \\value > 0xffff && ((\\value>>16) & 0xffff) != 0
    movk    \\reg,#(\\value>>16) & 0xffff,lsl #16
    .endif
    .if  \\value > 0xffffffff && ((\\value>>32) & 0xffff) != 0
    movk    \\reg,#(\\value>>32) & 0xffff,lsl #32
    .endif
    .if  \\value > 0xffffffffffff && ((\\value>>48) & 0xffff) != 0
    movk    \\reg,#(\\value>>48) & 0xffff,lsl #48
    .endif
    .endm

    .section .data.mmu
    .balign 2

    mmu_lock: .4byte 0                  // lock to ensure only 1 CPU runs init
#define LOCKED 1

    mmu_init: .4byte 0                  // whether init has been run
#define INITIALISED 1

    .section .text.mmu_on
    .balign 2
    .global mmu_on
    .type mmu_on, @function

mmu_on:

    ADRP    x0, mmu_lock                // get 4KB page containing mmu_lock
    ADD     x0, x0, :lo12:mmu_lock      // restore low 12 bits lost by ADRP
    MOV     w1, #LOCKED
    SEVL                                // first pass won't sleep
1:
    WFE                                 // sleep on retry
    LDAXR   w2, [x0]                    // read mmu_lock
    CBNZ    w2, 1b                      // not available, go back to sleep
    STXR    w3, w1, [x0]                // try to acquire mmu_lock
    CBNZ    w3, 1b                      // failed, go back to sleep

    ADRP    x6, {args.ttb}             // address of first table

check_already_initialised:
    ADRP    x1, mmu_init                // get 4KB page containing mmu_init
    LDR     w2, [x1,#:lo12:mmu_init]    // read mmu_init
    CBNZ    w2, end                     // init already done, skip to the end

zero_out_tables:
    mov     x2,x6
    MOV64   x3, {hex(args.tg * len(table.Table._allocated))}   // combined length of all tables
    LSR     x3, x3, #5                  // number of required STP instructions
    FMOV    d0, xzr                     // clear q0
1:
    STP     q0, q0, [x2], #32           // zero out 4 table entries at a time
    SUBS    x3, x3, #1
    B.NE    1b

load_descriptor_templates:
    MOV64     x2, {mmu.block_template(memory_type=mmap.MEMORY_TYPE.device)}       // Device block
    MOV64     x3, {mmu.page_template(memory_type=mmap.MEMORY_TYPE.device)}        // Device page
    MOV64     x4, {mmu.block_template(memory_type=mmap.MEMORY_TYPE.rw_data)}      // RW data block
    MOV64     x5, {mmu.page_template(memory_type=mmap.MEMORY_TYPE.rw_data)}       // RW data page
    MOV64    x20, {mmu.block_template(memory_type=mmap.MEMORY_TYPE.code)}      // code block
    MOV64    x21, {mmu.page_template(memory_type=mmap.MEMORY_TYPE.code)}       // code page
{_mk_asm()}

init_done:
    MOV     w2, #INITIALISED
    STR     w2, [x1]

end:
    MSR     {ttbr}_el{args.el}, x6
    .if {args.el} == 1
    MSR     {ttbro}_el1,xzr
    .endif
    MOV64   x1, {mmu.mair}             // program mair on this CPU
    MSR     mair_el{args.el}, x1
    MOV64   x1, {mmu.tcr}              // program tcr on this CPU
    MSR     tcr_el{args.el}, x1
    ISB
    MRS     x2, tcr_el{args.el}         // verify CPU supports desired config
    CMP     x2, x1
    B.NE    .
    MOV64   x1, {mmu.sctlr}            // program sctlr on this CPU
    MSR     sctlr_el{args.el}, x1
    ISB                                 // synchronize context on this CPU
    STLR    wzr, [x0]                   // release mmu_lock
    RET                                 // done!
    .balign 4
    .ltorg
"""

output = ""
for line in _tmp.splitlines():
    if "//" in line and not " * " in line:
        idx = line.index("//")
        code = line[:idx].rstrip()
        comment = line[idx:]
        line = f"{code}{' ' * (41 - len(code))}{comment}"
    output += f"{line}\n"

[log.verbose(line) for line in output.splitlines()]
