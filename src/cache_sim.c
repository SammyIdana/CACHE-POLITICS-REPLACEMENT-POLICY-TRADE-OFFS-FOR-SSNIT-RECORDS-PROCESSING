/*
 * cache_sim.c
 * -----------
 * CPEN 315/733 - Project 7: Cache Politics
 * Group 2 - Topic 7
 *
 * Trace-driven, configurable set-associative cache simulator.
 * Supports four replacement policies:
 *   - LRU     (Least Recently Used)
 *   - FIFO    (First In, First Out)
 *   - RANDOM  (uniformly random victim)
 *   - ARC     (Adaptive Replacement Cache - Megiddo & Modha, FAST '03)
 *
 * Usage:
 *   cache_sim --policy {lru,fifo,random,arc} --size <bytes> --assoc <ways>
 *             --block <bytes> --trace <file> [--seed <int>]
 *             [--hit-time <cycles>] [--miss-penalty <cycles>]
 *             [--out <csv-file>] [--label <string>]
 *
 * Trace file format: one decimal byte address per line. Lines beginning
 * with '#' are treated as comments and ignored.
 *
 * Output: a single summary line (human readable) plus, if --out is given,
 * an appended CSV row with the schema documented in README.md.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <time.h>

/* ---------------------------------------------------------------------
 * Configuration & CLI parsing
 * ------------------------------------------------------------------- */

typedef enum { POLICY_LRU, POLICY_FIFO, POLICY_RANDOM, POLICY_ARC, POLICY_OPT } policy_t;

typedef struct {
    policy_t policy;
    long     cache_size_bytes;
    int      assoc;
    int      block_size_bytes;
    char     trace_path[512];
    unsigned seed;
    double   hit_time_cycles;
    double   miss_penalty_cycles;
    char     out_path[512];
    char     label[128];
    int      have_out;
    char     dump_hits_path[512];
    int      have_dump_hits;
} config_t;

static void usage(const char *prog) {
    fprintf(stderr,
        "Usage: %s --policy {lru,fifo,random,arc} --size <bytes> --assoc <ways>\n"
        "          --block <bytes> --trace <file> [--seed <int>]\n"
        "          [--hit-time <cycles>] [--miss-penalty <cycles>]\n"
        "          [--out <csv-file>] [--label <string>] [--dump-hits <file>]\n"
        "Policies: lru, fifo, random, arc, opt (opt = Belady's offline optimal)\n", prog);
}

static policy_t parse_policy(const char *s) {
    if (strcmp(s, "lru") == 0)    return POLICY_LRU;
    if (strcmp(s, "fifo") == 0)   return POLICY_FIFO;
    if (strcmp(s, "random") == 0) return POLICY_RANDOM;
    if (strcmp(s, "arc") == 0)    return POLICY_ARC;
    if (strcmp(s, "opt") == 0)    return POLICY_OPT;
    fprintf(stderr, "Unknown policy '%s'\n", s);
    exit(1);
}

static const char *policy_name(policy_t p) {
    switch (p) {
        case POLICY_LRU:    return "LRU";
        case POLICY_FIFO:   return "FIFO";
        case POLICY_RANDOM: return "RANDOM";
        case POLICY_ARC:    return "ARC";
        case POLICY_OPT:    return "OPT";
    }
    return "?";
}

static void parse_args(int argc, char **argv, config_t *cfg) {
    memset(cfg, 0, sizeof(*cfg));
    cfg->seed = 42;
    cfg->hit_time_cycles = 1.0;
    cfg->miss_penalty_cycles = 100.0;
    strcpy(cfg->label, "run");
    int have_policy = 0, have_size = 0, have_assoc = 0, have_block = 0, have_trace = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--policy") == 0 && i + 1 < argc) {
            cfg->policy = parse_policy(argv[++i]); have_policy = 1;
        } else if (strcmp(argv[i], "--size") == 0 && i + 1 < argc) {
            cfg->cache_size_bytes = atol(argv[++i]); have_size = 1;
        } else if (strcmp(argv[i], "--assoc") == 0 && i + 1 < argc) {
            cfg->assoc = atoi(argv[++i]); have_assoc = 1;
        } else if (strcmp(argv[i], "--block") == 0 && i + 1 < argc) {
            cfg->block_size_bytes = atoi(argv[++i]); have_block = 1;
        } else if (strcmp(argv[i], "--trace") == 0 && i + 1 < argc) {
            strncpy(cfg->trace_path, argv[++i], sizeof(cfg->trace_path) - 1); have_trace = 1;
        } else if (strcmp(argv[i], "--seed") == 0 && i + 1 < argc) {
            cfg->seed = (unsigned) atoi(argv[++i]);
        } else if (strcmp(argv[i], "--hit-time") == 0 && i + 1 < argc) {
            cfg->hit_time_cycles = atof(argv[++i]);
        } else if (strcmp(argv[i], "--miss-penalty") == 0 && i + 1 < argc) {
            cfg->miss_penalty_cycles = atof(argv[++i]);
        } else if (strcmp(argv[i], "--out") == 0 && i + 1 < argc) {
            strncpy(cfg->out_path, argv[++i], sizeof(cfg->out_path) - 1); cfg->have_out = 1;
        } else if (strcmp(argv[i], "--label") == 0 && i + 1 < argc) {
            strncpy(cfg->label, argv[++i], sizeof(cfg->label) - 1);
        } else if (strcmp(argv[i], "--dump-hits") == 0 && i + 1 < argc) {
            strncpy(cfg->dump_hits_path, argv[++i], sizeof(cfg->dump_hits_path) - 1);
            cfg->have_dump_hits = 1;
        } else {
            fprintf(stderr, "Unrecognised argument: %s\n", argv[i]);
            usage(argv[0]); exit(1);
        }
    }
    if (!have_policy || !have_size || !have_assoc || !have_block || !have_trace) {
        fprintf(stderr, "Missing required argument(s).\n");
        usage(argv[0]); exit(1);
    }
    if ((cfg->cache_size_bytes % (cfg->assoc * cfg->block_size_bytes)) != 0) {
        fprintf(stderr, "size must be a multiple of assoc*block for clean set-associative geometry.\n");
        exit(1);
    }
}

/* ---------------------------------------------------------------------
 * Generic cache line bookkeeping shared by LRU / FIFO / RANDOM
 * ------------------------------------------------------------------- */

typedef struct {
    int      valid;
    uint64_t tag;
    uint64_t order_key; /* last-access time for LRU, insertion time for FIFO */
} line_t;

/* ---------------------------------------------------------------------
 * ARC per-set state (Megiddo & Modha, 2003)
 *
 * T1/T2 hold tags currently resident in the cache (recency- and
 * frequency-lists respectively). B1/B2 are *ghost* lists: metadata only
 * (tags), no data, used purely to adapt the target partition size p.
 * Lists are stored as simple arrays; index 0 = LRU end, last index = MRU
 * end. Associativity per set is small in this project (<=16), so O(n)
 * shifts on insert/evict are fine for trace sizes up to a few million.
 * ------------------------------------------------------------------- */

typedef struct {
    uint64_t *t1, *t2, *b1, *b2;
    int n1, n2, nb1, nb2;   /* current occupied counts */
    int cap;                /* = assoc (c), the max size of T1+T2 (and of each ghost list) */
    int p;                  /* adaptive target size for T1, 0 <= p <= cap */
} arc_set_t;

static void arc_list_remove_at(uint64_t *list, int *n, int idx) {
    for (int i = idx; i < *n - 1; i++) list[i] = list[i + 1];
    (*n)--;
}
static void arc_list_push_mru(uint64_t *list, int *n, int cap, uint64_t tag) {
    /* caller guarantees *n < cap before calling */
    list[(*n)++] = tag;
    (void) cap;
}
static int arc_list_find(uint64_t *list, int n, uint64_t tag) {
    for (int i = 0; i < n; i++) if (list[i] == tag) return i;
    return -1;
}

static arc_set_t *arc_set_init(int num_sets, int cap) {
    arc_set_t *sets = calloc(num_sets, sizeof(arc_set_t));
    for (int s = 0; s < num_sets; s++) {
        sets[s].t1 = calloc(cap, sizeof(uint64_t));
        sets[s].t2 = calloc(cap, sizeof(uint64_t));
        sets[s].b1 = calloc(cap, sizeof(uint64_t));
        sets[s].b2 = calloc(cap, sizeof(uint64_t));
        sets[s].cap = cap;
        sets[s].p = 0;
    }
    return sets;
}

/* REPLACE(x, p) per the paper: evict one line from cache (T1 or T2 LRU
 * end) and push its tag onto the corresponding ghost list (B1 or B2). */
static void arc_replace(arc_set_t *as, int x_in_b2) {
    if (as->n1 >= 1 && ((x_in_b2 && as->n1 == as->p) || (as->n1 > as->p))) {
        /* evict LRU of T1 -> MRU of B1 */
        uint64_t victim = as->t1[0];
        arc_list_remove_at(as->t1, &as->n1, 0);
        if (as->nb1 == as->cap) arc_list_remove_at(as->b1, &as->nb1, 0); /* keep ghost bounded */
        arc_list_push_mru(as->b1, &as->nb1, as->cap, victim);
    } else {
        uint64_t victim = as->t2[0];
        arc_list_remove_at(as->t2, &as->n2, 0);
        if (as->nb2 == as->cap) arc_list_remove_at(as->b2, &as->nb2, 0);
        arc_list_push_mru(as->b2, &as->nb2, as->cap, victim);
    }
}

/* Returns 1 on cache hit, 0 on miss. */
static int arc_access(arc_set_t *as, uint64_t tag) {
    int idx;

    /* Case I: hit in T1 or T2 */
    if ((idx = arc_list_find(as->t1, as->n1, tag)) >= 0) {
        arc_list_remove_at(as->t1, &as->n1, idx);
        arc_list_push_mru(as->t2, &as->n2, as->cap, tag);
        return 1;
    }
    if ((idx = arc_list_find(as->t2, as->n2, tag)) >= 0) {
        arc_list_remove_at(as->t2, &as->n2, idx);
        arc_list_push_mru(as->t2, &as->n2, as->cap, tag);
        return 1;
    }

    /* Case II: ghost hit in B1 -> grow p (favour recency) */
    if ((idx = arc_list_find(as->b1, as->nb1, tag)) >= 0) {
        int delta = (as->nb1 >= as->nb2) ? 1 : (int) ceil((double) as->nb2 / (double) as->nb1);
        as->p = as->p + delta; if (as->p > as->cap) as->p = as->cap;
        arc_replace(as, 0);
        arc_list_remove_at(as->b1, &as->nb1, idx);
        arc_list_push_mru(as->t2, &as->n2, as->cap, tag);
        return 0; /* was a miss for the *data* cache, hit only for the ghost metadata */
    }

    /* Case III: ghost hit in B2 -> shrink p (favour frequency) */
    if ((idx = arc_list_find(as->b2, as->nb2, tag)) >= 0) {
        int delta = (as->nb2 >= as->nb1) ? 1 : (int) ceil((double) as->nb1 / (double) as->nb2);
        as->p = as->p - delta; if (as->p < 0) as->p = 0;
        arc_replace(as, 1);
        arc_list_remove_at(as->b2, &as->nb2, idx);
        arc_list_push_mru(as->t2, &as->n2, as->cap, tag);
        return 0;
    }

    /* Case IV: genuinely new to this set */
    int l1 = as->n1 + as->nb1;
    if (l1 == as->cap) {
        if (as->n1 < as->cap) {
            arc_list_remove_at(as->b1, &as->nb1, 0);
            arc_replace(as, 0);
        } else {
            /* B1 empty, T1 full: evict LRU of T1 directly, no ghost insert */
            arc_list_remove_at(as->t1, &as->n1, 0);
        }
    } else if (l1 < as->cap && (as->n1 + as->n2 + as->nb1 + as->nb2) >= as->cap) {
        if ((as->n1 + as->n2 + as->nb1 + as->nb2) == 2 * as->cap)
            arc_list_remove_at(as->b2, &as->nb2, 0);
        arc_replace(as, 0);
    }
    arc_list_push_mru(as->t1, &as->n1, as->cap, tag);
    return 0;
}

/* ---------------------------------------------------------------------
 * OPT (Belady) support: offline optimal replacement.
 *
 * Requires whole-trace knowledge, so the trace is loaded into memory
 * up front (set_idx[]/tag[] arrays) regardless of policy -- trace
 * sizes in this project (tens of thousands of accesses) make this
 * trivial memory-wise, and it also gives every policy the same
 * --dump-hits capability for free.
 *
 * next_occurrence[i] = index of the next future access to the same
 * (set,tag) as access i, or INT64_MAX if it never recurs. Computed
 * with one backward pass using an open-addressing hash table keyed on
 * (set,tag).
 * ------------------------------------------------------------------- */

typedef struct { int used; int set; uint64_t tag; int64_t last_idx; } opt_hash_slot_t;

static uint64_t opt_hash(int set, uint64_t tag, uint64_t cap) {
    uint64_t h = ((uint64_t) set * 1099511628211ULL) ^ (tag * 14695981039346656037ULL);
    h ^= h >> 33; h *= 0xff51afd7ed558ccdULL; h ^= h >> 33;
    return h & (cap - 1);
}

static int64_t *opt_compute_next_occurrence(int *set_arr, uint64_t *tag_arr, long long n) {
    uint64_t cap = 16;
    while (cap < (uint64_t) n * 2) cap <<= 1;
    opt_hash_slot_t *table = calloc(cap, sizeof(opt_hash_slot_t));
    int64_t *nxt = malloc(n * sizeof(int64_t));

    for (long long i = n - 1; i >= 0; i--) {
        uint64_t h = opt_hash(set_arr[i], tag_arr[i], cap);
        while (table[h].used && !(table[h].set == set_arr[i] && table[h].tag == tag_arr[i]))
            h = (h + 1) & (cap - 1);
        nxt[i] = table[h].used ? table[h].last_idx : INT64_MAX;
        table[h].used = 1; table[h].set = set_arr[i]; table[h].tag = tag_arr[i]; table[h].last_idx = i;
    }
    free(table);
    return nxt;
}

typedef struct { int valid; uint64_t tag; int64_t next_use; } opt_line_t;

/* ---------------------------------------------------------------------
 * Main simulation
 * ------------------------------------------------------------------- */

int main(int argc, char **argv) {
    config_t cfg;
    parse_args(argc, argv, &cfg);
    srand(cfg.seed);

    int num_sets = (int) (cfg.cache_size_bytes / (cfg.assoc * cfg.block_size_bytes));
    int block_offset_bits = (int) log2((double) cfg.block_size_bytes);
    int index_bits = (int) log2((double) num_sets);

    FILE *tf = fopen(cfg.trace_path, "r");
    if (!tf) { fprintf(stderr, "Cannot open trace file %s\n", cfg.trace_path); return 1; }

    /* Pass 1: load the whole trace into memory as decomposed (set,tag) pairs. */
    long long cap_n = 4096, n = 0;
    int *set_arr = malloc(cap_n * sizeof(int));
    uint64_t *tag_arr = malloc(cap_n * sizeof(uint64_t));
    char line_buf[128];
    while (fgets(line_buf, sizeof(line_buf), tf)) {
        if (line_buf[0] == '#' || line_buf[0] == '\n') continue;
        if (n == cap_n) {
            cap_n *= 2;
            set_arr = realloc(set_arr, cap_n * sizeof(int));
            tag_arr = realloc(tag_arr, cap_n * sizeof(uint64_t));
        }
        uint64_t addr = strtoull(line_buf, NULL, 10);
        uint64_t block_addr = addr >> block_offset_bits;
        set_arr[n] = (int) (block_addr & (uint64_t) (num_sets - 1));
        tag_arr[n] = block_addr >> index_bits;
        n++;
    }
    fclose(tf);

    line_t *lines = NULL;
    arc_set_t *arc_sets = NULL;
    opt_line_t *opt_lines = NULL;
    int64_t *nxt = NULL;
    if (cfg.policy == POLICY_ARC) {
        arc_sets = arc_set_init(num_sets, cfg.assoc);
    } else if (cfg.policy == POLICY_OPT) {
        opt_lines = calloc((size_t) num_sets * cfg.assoc, sizeof(opt_line_t));
        nxt = opt_compute_next_occurrence(set_arr, tag_arr, n);
    } else {
        lines = calloc((size_t) num_sets * cfg.assoc, sizeof(line_t));
    }

    long long accesses = 0, hits = 0, misses = 0;
    uint64_t clock_counter = 0;
    char *hit_dump = cfg.have_dump_hits ? malloc((size_t) n) : NULL;

    for (long long i = 0; i < n; i++) {
        int set_idx = set_arr[i];
        uint64_t tag = tag_arr[i];

        accesses++;
        int hit = 0;

        if (cfg.policy == POLICY_ARC) {
            hit = arc_access(&arc_sets[set_idx], tag);
        } else if (cfg.policy == POLICY_OPT) {
            opt_line_t *set = &opt_lines[(size_t) set_idx * cfg.assoc];
            int found = -1, empty = -1;
            for (int w = 0; w < cfg.assoc; w++) {
                if (set[w].valid && set[w].tag == tag) { found = w; break; }
                if (!set[w].valid && empty < 0) empty = w;
            }
            if (found >= 0) {
                hit = 1;
                set[found].next_use = nxt[i];
            } else {
                int victim;
                if (empty >= 0) {
                    victim = empty;
                } else {
                    /* evict the resident line whose data is needed farthest
                     * in the future (or never again -- INT64_MAX sorts last) */
                    victim = 0;
                    for (int w = 1; w < cfg.assoc; w++)
                        if (set[w].next_use > set[victim].next_use) victim = w;
                }
                set[victim].valid = 1;
                set[victim].tag = tag;
                set[victim].next_use = nxt[i];
            }
        } else {
            line_t *set = &lines[(size_t) set_idx * cfg.assoc];
            int found = -1, empty = -1;
            for (int w = 0; w < cfg.assoc; w++) {
                if (set[w].valid && set[w].tag == tag) { found = w; break; }
                if (!set[w].valid && empty < 0) empty = w;
            }
            clock_counter++;
            if (found >= 0) {
                hit = 1;
                if (cfg.policy == POLICY_LRU) set[found].order_key = clock_counter;
                /* FIFO/RANDOM: order_key untouched on hit, by design */
            } else {
                int victim;
                if (empty >= 0) {
                    victim = empty;
                } else if (cfg.policy == POLICY_RANDOM) {
                    victim = rand() % cfg.assoc;
                } else { /* LRU or FIFO: evict min order_key */
                    victim = 0;
                    for (int w = 1; w < cfg.assoc; w++)
                        if (set[w].order_key < set[victim].order_key) victim = w;
                }
                set[victim].valid = 1;
                set[victim].tag = tag;
                set[victim].order_key = clock_counter;
            }
        }

        if (hit_dump) hit_dump[i] = hit ? '1' : '0';
        if (hit) hits++; else misses++;
    }

    if (hit_dump) {
        FILE *hf = fopen(cfg.dump_hits_path, "w");
        if (!hf) { fprintf(stderr, "Cannot open dump-hits file %s\n", cfg.dump_hits_path); return 1; }
        fwrite(hit_dump, 1, (size_t) n, hf);
        fputc('\n', hf);
        fclose(hf);
        free(hit_dump);
    }

    double hit_rate = accesses ? (double) hits / (double) accesses : 0.0;
    double miss_rate = 1.0 - hit_rate;
    double amat = cfg.hit_time_cycles + miss_rate * cfg.miss_penalty_cycles;

    printf("policy=%s size=%ld assoc=%d block=%d sets=%d accesses=%lld hits=%lld "
           "misses=%lld hit_rate=%.6f amat=%.4f trace=%s label=%s\n",
           policy_name(cfg.policy), cfg.cache_size_bytes, cfg.assoc, cfg.block_size_bytes,
           num_sets, accesses, hits, misses, hit_rate, amat, cfg.trace_path, cfg.label);

    if (cfg.have_out) {
        int need_header = 0;
        FILE *check = fopen(cfg.out_path, "r");
        if (!check) need_header = 1; else fclose(check);
        FILE *of = fopen(cfg.out_path, "a");
        if (!of) { fprintf(stderr, "Cannot open output file %s\n", cfg.out_path); return 1; }
        if (need_header)
            fprintf(of, "label,policy,cache_size,assoc,block_size,num_sets,trace,"
                        "accesses,hits,misses,hit_rate,miss_rate,hit_time,miss_penalty,amat\n");
        fprintf(of, "%s,%s,%ld,%d,%d,%d,%s,%lld,%lld,%lld,%.6f,%.6f,%.4f,%.4f,%.4f\n",
                cfg.label, policy_name(cfg.policy), cfg.cache_size_bytes, cfg.assoc,
                cfg.block_size_bytes, num_sets, cfg.trace_path, accesses, hits, misses,
                hit_rate, miss_rate, cfg.hit_time_cycles, cfg.miss_penalty_cycles, amat);
        fclose(of);
    }

    if (lines) free(lines);
    if (opt_lines) free(opt_lines);
    if (nxt) free(nxt);
    if (arc_sets) {
        for (int s = 0; s < num_sets; s++) {
            free(arc_sets[s].t1); free(arc_sets[s].t2);
            free(arc_sets[s].b1); free(arc_sets[s].b2);
        }
        free(arc_sets);
    }
    free(set_arr);
    free(tag_arr);
    return 0;
}
