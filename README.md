# arm64-pgtable-tool

This version has been changed a lot for my personal preferences. For the original version go to

[arm64-pgtable-tool](https://github.com/ashwio/arm64-pgtable-tool).

## Introduction

Tool for automatically generating MMU and translation table setup code, whether to drag and drop into your own bare metal arm64 projects or to assist you in your own learning.

For more information see [my blog post](https://ashw.io/blog/arm64-pgtable-tool).

## Prerequisites

* Python 3.8+
* [chaimleib's IntervalTree](https://github.com/chaimleib/intervaltree)

```
    pip install intervaltree
```

## Usage

The following command-line options are available:

```
    -i SRC                  input memory map file
    -o DST                  output GNU assembly file (default: mmu_setup.S)
    -ttb TTB                symbol of the table base (default mmu_table)
    -el {1,2,3}             exception level (default: 1)
    -tg {4K,16K,64K}        translation granule (default: 4K)
    -tsz {32,36,40,48}      address space size (default: 40)
    -ttbr1                  use TTBR1 instead of TTBR0 in EL1 (default ttbr0)
    -no_mmuon               Do not generate mmu_on function (default: on)
    -l label                append <lable> to the generated function (default: empty)
```

### Input memory map file

The input memory map file is a simple comma-separated text file with format:

```
    ADDRESS, LENGTH, TYPE, LABEL
```

Empty lines are allowed. Comments must start with `#`.

Where:

* `ADDRESS` is the hexadecimal base address of the region;
* `LENGTH` is the length of the region in bytes, using `K`, `M`, or `G` to specify the unit;
* `TYPE` is either `DEVICE` for Device-nGnRnE or `RW_DATA` for Normal Inner/Outer Write-Back RAWA Inner Shareable or `CODE` for Normal Read-only executable;
* `LABEL` is a human-friendly label describing what is being mapped. (For a nicer output, limit to 16 chars)

Several memory map files are provided in the [examples folder](examples).

### Translation table base address

This must be the base address of a granule aligned buffer that is at least large enough to contain the number of translation tables allocated by the tool.

You can see this in the generated GNU assembly file:

```
    /*
     * ...
     *
     * This memory map requires a total of 7 translation tables.
     * Each table occupies 4K of memory (0x1000 bytes).
     * The buffer pointed to by "mmu_table" is therefore 7x 4K = 0x7000 bytes long.
     *
     * ...
     */
```

It is also your responsibility to ensure the memory region containing the buffer is described as `NORMAL` in the input memory map file.

### Exception level

The tool only programs `TTBR0_ELn` at the specified exception level. Where two virtual address spaces are available, such as at EL1, the higher virtual address space pointed to by `TTBR1_ELn` is disabled.

The tool currently has no concept of two security states. If running in the Secure world, all entries default to Secure.

If **EL1** is chosen, the other `TTBRx` is cleared.

### Translation table

By default `TTBR0` is used. With the option `-ttbr1`, one can use `TTBR1`, but only in **EL1**.

### Translation granule

The `4K` and `64K` granules have been tested on the Armv8-A Foundation Platform FVP. Unfortunately the `16K` granule is not supported by this FVP so has not been tested.

### Address space size

The tool only generates 1-to-1 mappings, often referred to as a "flat map" or "identity map". With this in mind, only a limited subset of possible virtual address space sizes are supported, corresponding to the available physical address space sizes defined by the Armv8-A architecture.

## Example output

Running the following command:

```
    python3.8 generate.py -i examples/base-fvp-minimal.txt
```

Where `examples/base-fvp-minimal.txt` contains:

```
    0x01C090000,   4K, DEVICE, UART0
    0x02C000000,   8K, DEVICE, GICC
    0x02E000000,  64K, NORMAL, Non-Trusted SRAM
    0x02F000000,  64K, DEVICE, GICv3 GICD
    0x02F100000,   1M, DEVICE, GICv3 GICR
    0x080000000,   1G, NORMAL, Non-Trusted DRAM
    0x0C0000000,   2M, CODE, CODE
```

Generates the following `mmu_setup.S` GNU assembly file:

```
/*
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
 * level 0 table @ mmu_table + 0x0
 * [#   0]-------------------------------\
 *     level 1 table @ mmu_table + 0x1000
 *     [#   0]-------------------------------\
 *         level 2 table @ mmu_table + 0x2000
 *         [# 224]-------------------------------\
 *             level 3 table @ mmu_table + 0x3000
 *             [# 144] 0x00001c090000-0x00001c090fff,   Device,            UART0
 *         [# 352]-------------------------------\
 *             level 3 table @ mmu_table + 0x4000
 *             [#   0] 0x00002c000000-0x00002c000fff,   Device,             GICC
 *             [#   1] 0x00002c001000-0x00002c001fff,   Device,             GICC
 *         [# 368]-------------------------------\
 *             level 3 table @ mmu_table + 0x5000
 *             [#   0] 0x00002e000000-0x00002e000fff,  RW_Data, Non-Trusted SRAM
 *                     ...
 *             [#  15] 0x00002e00f000-0x00002e00ffff,  RW_Data, Non-Trusted SRAM
 *         [# 376]-------------------------------\
 *             level 3 table @ mmu_table + 0x6000
 *             [#   0] 0x00002f000000-0x00002f000fff,   Device,       GICv3 GICD
 *                     ...
 *             [#  15] 0x00002f00f000-0x00002f00ffff,   Device,       GICv3 GICD
 *             [# 256] 0x00002f100000-0x00002f100fff,   Device,       GICv3 GICR
 *                     ...
 *             [# 511] 0x00002f1ff000-0x00002f1fffff,   Device,       GICv3 GICR
 *     [#   2] 0x000080000000-0x0000bfffffff,          RW_Data, Non-Trusted DRAM
 *     [#   3]-------------------------------\
 *         level 2 table @ mmu_table + 0x7000
 *         [#   0] 0x0000c0000000-0x0000c01fffff,         Code,             CODE
 *
 * The following command line arguments were passed to arm64-pgtable-tool:
 *
 *      -i examples/base-fvp-minimal.txt
 *      -ttb mmu_table
 *      -el 1
 *      -tg 4K
 *      -tsz 40
 *
 * This memory map requires a total of 8 translation tables.
 * Each table occupies 4K of memory (0x1000 bytes).
 * The buffer pointed to by 'mmu_table' is therefore 8x4K = 0x8000 bytes long.
 *
 * The programmer must also ensure that the virtual memory region containing the
 * translation tables is itself marked as NORMAL in the memory map file.
 */

     /* some handy macros */
    .macro  FUNC64 name
    .section .text.\name,"ax"
    .type   \name,%function
    .globl  \name
\name:
    .endm

    .macro  ENDFUNC name
    .align  3
    .pool
    .globl  \name\()_end
\name\()_end:
    .size   \name,.-\name
    .endm

    .macro  MOV64 reg,value
    movz    \reg,#\value & 0xffff
    .if \value > 0xffff && ((\value>>16) & 0xffff) != 0
    movk    \reg,#(\value>>16) & 0xffff,lsl #16
    .endif
    .if \value > 0xffffffff && ((\value>>32) & 0xffff) != 0
    movk    \reg,#(\value>>32) & 0xffff,lsl #32
    .endif
    .if \value > 0xffffffffffff && ((\value>>48) & 0xffff) != 0
    movk    \reg,#(\value>>48) & 0xffff,lsl #48
    .endif
    .endm

/**
 * Setup the page table.
 * Not reentrant!
 */
    FUNC64 pagetable_init
    adrp    x20, mmu_table
/* zero_out_tables */
    mov     x2,x20
    MOV64   x3, 0x8000                   // combined length of all tables
    fmov    d0, xzr                      // clear q0
1:
    stp     q0, q0, [x2], #32            // zero out 4 table entries at a time
    subs    x3, x3, #32
    b.ne    1b

/* load_descriptor_templates */
    MOV64    x2, 0x20000000000705        // Device block
    MOV64    x3, 0x20000000000707        // Device page
    MOV64    x4, 0x20000000000701        // RW data block
    MOV64    x5, 0x20000000000703        // RW data page
    MOV64    x6, 0x20000000000709        // no_cache block
    MOV64    x7, 0x2000000000070b        // no_cache page
    MOV64    x8, 0x781                   // code block
    MOV64    x9, 0x783                   // code page

/* program_table_0 */
    MOV64   x21, 0x0                     // base address of this table
    add     x21, x21, x20                // add global base
    MOV64   x22, 0x8000000000            // chunk size
/* program_table_0_entry_0 */
    MOV64   x10, 0                       // idx
    MOV64   x11, 0x1000                  // next-level table address
    add     x11, x11, x20                // add base address
    orr     x11, x11, #0x3               // next-level table descriptor
    str     x11, [x21, x10, lsl #3]      // write entry into table
/* program_table_1 */
    MOV64   x21, 0x1000                  // base address of this table
    add     x21, x21, x20                // add global base
    MOV64   x22, 0x40000000              // chunk size
/* program_table_1_entry_0 */
    MOV64   x10, 0                       // idx
    MOV64   x11, 0x2000                  // next-level table address
    add     x11, x11, x20                // add base address
    orr     x11, x11, #0x3               // next-level table descriptor
    str     x11, [x21, x10, lsl #3]      // write entry into table
/* program_table_1_entry_2 */
/* Non-Trusted DRAM */
    MOV64   x10, 2                       // idx
    MOV64   x12, 0x80000000              // output address of entry[idx]
    orr     x12, x12, x4                 // merge output address with template
    str     X12, [x21, x10, lsl #3]      // write entry into table

/* program_table_1_entry_3 */
    MOV64   x10, 3                       // idx
    MOV64   x11, 0x7000                  // next-level table address
    add     x11, x11, x20                // add base address
    orr     x11, x11, #0x3               // next-level table descriptor
    str     x11, [x21, x10, lsl #3]      // write entry into table
/* program_table_2 */
    MOV64   x21, 0x2000                  // base address of this table
    add     x21, x21, x20                // add global base
    MOV64   x22, 0x200000                // chunk size
/* program_table_2_entry_224 */
    MOV64   x10, 224                     // idx
    MOV64   x11, 0x3000                  // next-level table address
    add     x11, x11, x20                // add base address
    orr     x11, x11, #0x3               // next-level table descriptor
    str     x11, [x21, x10, lsl #3]      // write entry into table
/* program_table_2_entry_352 */
    MOV64   x10, 352                     // idx
    MOV64   x11, 0x4000                  // next-level table address
    add     x11, x11, x20                // add base address
    orr     x11, x11, #0x3               // next-level table descriptor
    str     x11, [x21, x10, lsl #3]      // write entry into table
/* program_table_2_entry_368 */
    MOV64   x10, 368                     // idx
    MOV64   x11, 0x5000                  // next-level table address
    add     x11, x11, x20                // add base address
    orr     x11, x11, #0x3               // next-level table descriptor
    str     x11, [x21, x10, lsl #3]      // write entry into table
/* program_table_2_entry_376 */
    MOV64   x10, 376                     // idx
    MOV64   x11, 0x6000                  // next-level table address
    add     x11, x11, x20                // add base address
    orr     x11, x11, #0x3               // next-level table descriptor
    str     x11, [x21, x10, lsl #3]      // write entry into table
/* program_table_3 */
    MOV64   x21, 0x3000                  // base address of this table
    add     x21, x21, x20                // add global base
    MOV64   x22, 0x1000                  // chunk size
/* program_table_3_entry_144 */
/* UART0 */
    MOV64   x10, 144                     // idx
    MOV64   x12, 0x1c090000              // output address of entry[idx]
    orr     x12, x12, x3                 // merge output address with template
    str     X12, [x21, x10, lsl #3]      // write entry into table

/* program_table_4 */
    MOV64   x21, 0x4000                  // base address of this table
    add     x21, x21, x20                // add global base
    MOV64   x22, 0x1000                  // chunk size
/* program_table_4_entry_0_to_1 */
/* GICC */
    MOV64   x10, 0                       // idx
    MOV64   x11, 2                       // number of contiguous entries
    MOV64   x12, 0x2c000000              // output address of entry[idx]
1:
    orr     x12, x12, x3                 // merge output address with template
    str     X12, [x21, x10, lsl #3]      // write entry into table
    add     x10, x10, #1                 // prepare for next entry
    add     x12, x12, x22                // add chunk to address
    subs    x11, x11, #1                 // loop as required
    b.ne    1b

/* program_table_5 */
    MOV64   x21, 0x5000                  // base address of this table
    add     x21, x21, x20                // add global base
    MOV64   x22, 0x1000                  // chunk size
/* program_table_5_entry_0_to_15 */
/* Non-Trusted SRAM */
    MOV64   x10, 0                       // idx
    MOV64   x11, 16                      // number of contiguous entries
    MOV64   x12, 0x2e000000              // output address of entry[idx]
1:
    orr     x12, x12, x5                 // merge output address with template
    str     X12, [x21, x10, lsl #3]      // write entry into table
    add     x10, x10, #1                 // prepare for next entry
    add     x12, x12, x22                // add chunk to address
    subs    x11, x11, #1                 // loop as required
    b.ne    1b

/* program_table_6 */
    MOV64   x21, 0x6000                  // base address of this table
    add     x21, x21, x20                // add global base
    MOV64   x22, 0x1000                  // chunk size
/* program_table_6_entry_0_to_15 */
/* GICv3 GICD */
    MOV64   x10, 0                       // idx
    MOV64   x11, 16                      // number of contiguous entries
    MOV64   x12, 0x2f000000              // output address of entry[idx]
1:
    orr     x12, x12, x3                 // merge output address with template
    str     X12, [x21, x10, lsl #3]      // write entry into table
    add     x10, x10, #1                 // prepare for next entry
    add     x12, x12, x22                // add chunk to address
    subs    x11, x11, #1                 // loop as required
    b.ne    1b

/* program_table_6_entry_256_to_511 */
/* GICv3 GICR */
    MOV64   x10, 256                     // idx
    MOV64   x11, 256                     // number of contiguous entries
    MOV64   x12, 0x2f100000              // output address of entry[idx]
1:
    orr     x12, x12, x3                 // merge output address with template
    str     X12, [x21, x10, lsl #3]      // write entry into table
    add     x10, x10, #1                 // prepare for next entry
    add     x12, x12, x22                // add chunk to address
    subs    x11, x11, #1                 // loop as required
    b.ne    1b

/* program_table_7 */
    MOV64   x21, 0x7000                  // base address of this table
    add     x21, x21, x20                // add global base
    MOV64   x22, 0x200000                // chunk size
/* program_table_7_entry_0 */
/* CODE */
    MOV64   x10, 0                       // idx
    MOV64   x12, 0xc0000000              // output address of entry[idx]
    orr     x12, x12, x8                 // merge output address with template
    str     X12, [x21, x10, lsl #3]      // write entry into table

    ret                                  // done!
    ENDFUNC pagetable_init

    .section noinit.mmu
mmu_table: .space 0x8000

/*
 * Set translation table and enable MMU
 */
    FUNC64 mmu_on
    adrp    x1, mmu_init                 // get 4KB page containing mmu_init
    ldr     w2, [x1,#:lo12:mmu_init]     // read mmu_init
    cbz     w2, .                        // init not done, endless loop

    adrp    x6, mmu_table                // address of first table
    msr     ttbr0_el1, x6
    .if 1 == 1
    msr     ttbr1_el1,xzr
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
    MOV64   x1, 0xbb44ff00               // program mair on this CPU
    msr     mair_el1, x1
    MOV64   x1, 0x200803518              // program tcr on this CPU
    msr     tcr_el1, x1
    isb
    msr     x2, tcr_el1                  // verify CPU supports desired config
    cmp     x2, x1
    b.ne    .
    MOV64   x1, 0x1005                   // program sctlr on this CPU
    msr     sctlr_el1, x1
    isb                                  // synchronize context on this CPU
    ret
    ENDFUNC mmu_on
```
