# Story: Token bucket rate limiter

<!-- pdd-story-prompts: token_bucket_python.prompt -->

## Context

A rate limiter service uses a token bucket to throttle consume requests.
Each caller starts with a full bucket and drains it as requests are made.
A background job periodically calls refill to restore tokens.

## Acceptance Criteria

- [ ] R1: A consume request for more tokens than available is rejected (returns False) and the bucket is unchanged
- [ ] R2: A successful consume reduces tokens_available by exactly the requested amount
- [ ] R3: A refill call never sets tokens_available above the bucket's capacity
- [ ] R4: Creating a bucket with a non-positive capacity raises ValueError

## Scenarios

### Happy path — consume within budget
Given a bucket with capacity=10 and tokens_available=10
When consume(3) is called
Then the result is True
And tokens_available equals 7

### R1 — rejection when insufficient tokens
Given a bucket with capacity=10 and tokens_available=2
When consume(5) is called
Then the result is False
And tokens_available remains 2

### R2 — exact state transition on success
Given a bucket with capacity=10 and tokens_available=8
When consume(3) is called
Then tokens_available equals exactly 5

### R3 — refill never exceeds capacity
Given a bucket with capacity=10 and tokens_available=9
When refill(50) is called
Then tokens_available equals 10

### R3 — refill from empty stays within capacity
Given a bucket with capacity=5 and tokens_available=0
When refill(100) is called
Then tokens_available equals 5
And tokens_available <= capacity

### R4 — invalid capacity rejected at construction
Given capacity=0
When TokenBucket(capacity=0) is called
Then ValueError is raised

Given capacity=-1
When TokenBucket(capacity=-1) is called
Then ValueError is raised
