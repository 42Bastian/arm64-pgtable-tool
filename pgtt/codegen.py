"""
Copyright (c) 2019 Ash Wilding. All rights reserved.
          (c) 2021 42Bastian Schick

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
/* program_table_{n} */
    MOV64   x21, {hex(t.addr)}          // base address of this table
    add     x21, x21, x20          // add global base
    MOV64   x22, {hex(t.chunk)}         // chunk size"""

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
    elif r.memory_type == mmap.MEMORY_TYPE.no_cache:
        template_reg = "x6" if t.level < 3 else "x7"
    else:
        template_reg = "x8" if t.level < 3 else "x9"

    if r.num_contig > 1:
        return f"""
/* program_table_{n}_entry_{idx}_to_{idx + r.num_contig - 1} */
/* {r.label} */
    MOV64   x10, {idx}                 // idx
    MOV64   x11, {r.num_contig}         // number of contiguous entries
    MOV64   x12, {hex(r.addr)}         // output address of entry[idx]
1:
    orr     x12, x12, {template_reg}    // merge output address with template
    str     X12, [x21, x10, lsl #3]      // write entry into table
    add     x10, x10, #1                // prepare for next entry
    add     x12, x12, x22                // add chunk to address
    subs    x11, x11, #1                // loop as required
    b.ne    1b
"""
    else:
        return f"""
/* program_table_{n}_entry_{idx} */
/* {r.label} */
    MOV64   x10, {idx}                 // idx
    MOV64   x12, {hex(r.addr)}         // output address of entry[idx]
    orr     x12, x12, {template_reg}    // merge output address with template
    str     X12, [x21, x10, lsl #3]      // write entry into table
"""



def _mk_next_level_table( n:int, idx:int, next_t:table.Table ) -> str:
    """
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
/* program_table_{n}_entry_{idx} */
    MOV64   x10, {idx}                 // idx
    MOV64   x11, {hex(next_t.addr)}    // next-level table address
    add     x11, x11, x20              // add base address
    orr     x11, x11, #0x3             // next-level table descriptor
    str     x11, [x21, x10, lsl #3]     // write entry into table"""


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
 * See: https://github.com/42Bastian Schick/arm64-pgtable-tool
 * Forked from: https://github.com/ashwio/arm64-pgtable-tool
 *
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
 *
 * The programmer must also ensure that the virtual memory region containing the
 * translation tables is itself marked as NORMAL in the memory map file.
 */

     /* some handy macros */
    .macro  FUNC64 name
    .section .text.\\name,"ax"
    .type   \\name,%function
    .globl  \\name
\\name:
    .endm

    .macro  ENDFUNC name
    .align  3
    .pool
    .globl  \\name\\()_end
\\name\\()_end:
    .size   \\name,.-\\name
    .endm

    .macro  MOV64 reg,value
    movz    \\reg,#\\value & 0xffff
    .if \\value > 0xffff && ((\\value>>16) & 0xffff) != 0
    movk    \\reg,#(\\value>>16) & 0xffff,lsl #16
    .endif
    .if \\value > 0xffffffff && ((\\value>>32) & 0xffff) != 0
    movk    \\reg,#(\\value>>32) & 0xffff,lsl #32
    .endif
    .if \\value > 0xffffffffffff && ((\\value>>48) & 0xffff) != 0
    movk    \\reg,#(\\value>>48) & 0xffff,lsl #48
    .endif
    .endm

/**
 * Setup the page table.
 * Not reentrant!
 */
    FUNC64 pagetable_init{args.label}
    adrp    x20, {args.ttb}
/* zero_out_tables */
    mov     x2,x20
    MOV64   x3, {hex(args.tg * len(table.Table._allocated))}   // combined length of all tables
    fmov    d0, xzr                     // clear q0
1:
    stp     q0, q0, [x2], #32           // zero out 4 table entries at a time
    subs    x3, x3, #32
    b.ne    1b

/* load_descriptor_templates */
    MOV64    x2, {mmu.block_template(memory_type=mmap.MEMORY_TYPE.device)}   // Device block
    MOV64    x3, {mmu.page_template(memory_type=mmap.MEMORY_TYPE.device)}    // Device page
    MOV64    x4, {mmu.block_template(memory_type=mmap.MEMORY_TYPE.rw_data)}  // RW data block
    MOV64    x5, {mmu.page_template(memory_type=mmap.MEMORY_TYPE.rw_data)}   // RW data page
    MOV64    x6, {mmu.block_template(memory_type=mmap.MEMORY_TYPE.no_cache)} // no_cache block
    MOV64    x7, {mmu.page_template(memory_type=mmap.MEMORY_TYPE.no_cache)}  // no_cache page
    MOV64    x8, {mmu.block_template(memory_type=mmap.MEMORY_TYPE.code)}     // code block
    MOV64    x9, {mmu.page_template(memory_type=mmap.MEMORY_TYPE.code)}      // code page
{_mk_asm()}
    ret                                 // done!
    ENDFUNC pagetable_init{args.label}

    .section noinit.mmu
{args.ttb}: .space {hex(args.tg * len(table.Table._allocated))}
"""

mmu_on = f"""
/*
 * Set translation table and enable MMU
 */
    FUNC64 mmu_on
    adrp    x1, mmu_init               // get 4KB page containing mmu_init
    ldr     w2, [x1,#:lo12:mmu_init]   // read mmu_init
    cbz     w2, .                      // init not done, endless loop

    adrp    x6, {args.ttb}             // address of first table
    msr     {ttbr}_el{args.el}, x6
    .if {args.el} == 1
    msr     {ttbro}_el1,xzr
    .endif
    /**********************************************
    * Set up memory attributes
    * This equates to:
    * 0 = b00000000 = Device-nGnRnE
    * 1 = b11111111 = Normal, Inner/Outer WB/WA/RA
    * 2 = b01000100 = Normal, Inner/Outer Non-Cacheable
    * 3 = b10111011 = Normal, Inner/Outer WT/WA/RA
    **********************************************/

    msr MAIR_EL1, x1
    MOV64   x1, {mmu.mair}             // program mair on this CPU
    msr     mair_el{args.el}, x1
    MOV64   x1, {mmu.tcr}              // program tcr on this CPU
    msr     tcr_el{args.el}, x1
    isb
    msr     x2, tcr_el{args.el}         // verify CPU supports desired config
    cmp     x2, x1
    b.ne    .
    MOV64   x1, {mmu.sctlr}            // program sctlr on this CPU
    msr     sctlr_el{args.el}, x1
    isb                                 // synchronize context on this CPU
    ret
    ENDFUNC mmu_on
"""

output = ""
for line in _tmp.splitlines():
    if "//" in line and not " * " in line:
        idx = line.index("//")
        code = line[:idx].rstrip()
        comment = line[idx:]
        line = f"{code}{' ' * (41 - len(code))}{comment}"
    output += f"{line}\n"
if not args.no_mmuon:
    for line in mmu_on.splitlines():
        if "//" in line and not " * " in line:
            idx = line.index("//")
            code = line[:idx].rstrip()
            comment = line[idx:]
            line = f"{code}{' ' * (41 - len(code))}{comment}"
        output += f"{line}\n"

[log.verbose(line) for line in output.splitlines()]
