docs/19_APPROVED_STACK/03_AI_AND_LLM_FRAMEWORKS.md

# AI AND LLM FRAMEWORKS

**Document ID:** JAS-AS-03

**Version:** 1.0

**Status:** APPROVED

**Classification:** Approved Stack

**Layer:** Artificial Intelligence Infrastructure

---

# 1. Purpose

This document defines the officially approved Artificial Intelligence and Large Language Model (LLM) framework stack for the JARVIS ecosystem.

Its purpose is to establish a standardized AI orchestration layer capable of supporting enterprise-grade conversational intelligence, autonomous reasoning, planning, memory interaction, tool execution, multimodal workflows, and future cognitive capabilities while remaining fully aligned with the JAS architecture.

The selected frameworks shall become the authoritative implementation reference for Version Lock, Manifest, Bootstrap, Architecture Compliance Checker, and Core Development.

---

# 2. Scope

This document governs every framework responsible for:

- LLM abstraction
- Agent execution
- Tool orchestration
- Prompt execution
- Structured output
- Function calling
- Workflow orchestration
- Streaming
- Multimodal interaction
- Long-context management
- Retrieval integration
- Model interoperability
- Vendor abstraction
- Future AI expansion

Model selection itself is covered by:

**19_APPROVED_MODELS.md**

---

# 3. Definitions

## AI Framework

A software framework responsible for communication between JARVIS and AI models.

---

## Agent Framework

A framework capable of orchestrating reasoning loops, planning, tools, memory and autonomous execution.

---

## Model Provider

A service capable of hosting one or more language models.

Examples:

- OpenAI
- Anthropic
- Google
- Ollama
- Azure
- OpenRouter
- Together AI

---

## Tool Calling

The standardized mechanism allowing language models to invoke external capabilities.

---

## Structured Output

Machine-readable responses validated through schemas rather than natural language parsing.

---

# 4. Architectural Principles

The AI layer SHALL follow these principles.

## Provider Independence

JARVIS SHALL never become permanently coupled to a single AI provider.

---

## Model Independence

Frameworks SHALL abstract model implementations.

Switching models SHALL require minimal architectural changes.

---

## Stateless Core

Frameworks SHALL not become the primary state storage mechanism.

Persistent memory belongs exclusively to the Memory Architecture.

---

## Deterministic Tool Execution

AI frameworks SHALL never execute tools directly without passing through the Tool Execution Layer defined by JAS.

---

## Layer Separation

Frameworks SHALL not implement:

- Memory
- Browser
- Voice
- Vision
- Security
- Planning persistence

Those responsibilities belong to dedicated architectural layers.

---

# 5. Evaluation Criteria

Candidate frameworks are evaluated using:

- Project maturity
- Community size
- Enterprise adoption
- Documentation quality
- API stability
- Release cadence
- Long-term maintainability
- Structured output support
- Streaming support
- Async capabilities
- Multi-provider support
- Tool calling maturity
- Memory compatibility
- LangGraph compatibility
- MCP compatibility
- Python ecosystem compatibility
- License compatibility
- Performance
- Security history
- Extensibility

---

# 6. Candidate Technologies

The following frameworks were evaluated.

## LangChain

Status:

Candidate

Purpose:

General AI abstraction framework.

---

## LangGraph

Status:

Candidate

Purpose:

Stateful agent orchestration.

---

## PydanticAI

Status:

Candidate

Purpose:

Structured AI interactions.

---

## LlamaIndex

Status:

Candidate

Purpose:

Knowledge retrieval.

---

## Haystack

Status:

Candidate

Purpose:

Enterprise RAG platform.

---

## Semantic Kernel

Status:

Candidate

Purpose:

Microsoft AI orchestration.

---

## AutoGen

Status:

Candidate

Purpose:

Multi-agent conversations.

---

## CrewAI

Status:

Candidate

Purpose:

Agent collaboration.

---

## DSPy

Status:

Candidate

Purpose:

Prompt optimization.

---

## Guidance

Status:

Candidate

Purpose:

Controlled prompt generation.

---

# 7. High-Level Architecture

The approved AI stack SHALL consist of multiple complementary layers instead of relying on a single framework.

Layer 1

Provider abstraction

↓

Layer 2

Structured interaction

↓

Layer 3

Workflow orchestration

↓

Layer 4

Planning

↓

Layer 5

Memory integration

↓

Layer 6

Tool execution

↓

Layer 7

Response generation

No individual framework SHALL own the complete execution pipeline.

---

# 8. LangChain Evaluation

## Purpose

General-purpose AI abstraction.

---

## Advantages

- Massive ecosystem
- Mature integrations
- Excellent provider support
- Active maintenance
- Strong documentation
- Rapid feature evolution

---

## Weaknesses

- Large dependency graph
- API evolution requires monitoring
- Some abstractions increase complexity

---

## Enterprise Readiness

High

---

## Long-Term Viability

Excellent

---

## Decision

Approved

Role:

Provider abstraction and ecosystem integration.

---

# 9. LangGraph Evaluation

## Purpose

Stateful graph-based orchestration.

---

## Advantages

- Durable execution
- Cyclic workflows
- Human-in-the-loop support
- Recovery support
- Agent orchestration
- Parallel execution
- Checkpointing
- Native LangChain integration

---

## Weaknesses

- Learning curve
- Rapid feature evolution

---

## Enterprise Readiness

Excellent

---

## Long-Term Viability

Excellent

---

## Decision

Approved

Primary orchestration framework.

---

# 10. PydanticAI Evaluation

## Purpose

Reliable structured interactions.

---

## Advantages

- Schema-first design
- Excellent validation
- Type safety
- Native Python integration
- Predictable outputs
- Clean API

---

## Weaknesses

- Smaller ecosystem
- Younger project

---

## Enterprise Readiness

High

---

## Long-Term Viability

High

---

## Decision

Approved

Primary structured output framework.

---

# 11. LlamaIndex Evaluation

## Purpose

Knowledge retrieval.

---

## Advantages

- Excellent RAG support
- Document indexing
- Large connector ecosystem
- Mature retrieval techniques

---

## Weaknesses

- Overlaps with LangChain
- Additional complexity

---

## Enterprise Readiness

High

---

## Decision

Conditionally Approved

Used where advanced retrieval significantly exceeds LangChain capabilities.

---

# 12. Haystack Evaluation

## Purpose

Enterprise Retrieval-Augmented Generation.

---

## Advantages

- Mature RAG architecture
- Production deployments
- Strong search pipeline
- Flexible indexing

---

## Weaknesses

- Considerable operational complexity
- Significant overlap with existing architecture

---

## Decision

Experimental

Reserved for future enterprise deployments requiring dedicated search infrastructure.

## 13. Semantic Kernel Evaluation

### Purpose

Microsoft-oriented orchestration framework focused on enterprise AI integration, planner abstractions, memory connectors, and plugin execution.

---

### Advantages

- Strong Microsoft ecosystem support
- Good Azure OpenAI integration
- Enterprise governance features
- Mature plugin abstractions
- Well-designed planning concepts
- Active commercial backing

---

### Weaknesses

- Primarily optimized for Microsoft ecosystem
- Less community adoption than LangChain
- Smaller third-party integration ecosystem
- Reduced flexibility for provider-neutral architectures

---

### Enterprise Readiness

Excellent

---

### Long-Term Viability

High

---

### Decision

Conditionally Approved

Semantic Kernel MAY be adopted for enterprise integrations requiring deep Microsoft ecosystem interoperability.

It SHALL NOT become the primary orchestration framework for JARVIS Core.

---

# 14. AutoGen Evaluation

## Purpose

Multi-agent conversational orchestration framework developed for autonomous AI collaboration.

---

## Advantages

- Native multi-agent communication
- Autonomous conversation loops
- Flexible delegation
- Research-oriented innovation
- Strong academic foundation
- Good experimentation capabilities

---

## Weaknesses

- Rapid API evolution
- Less deterministic execution
- Limited production maturity compared to LangGraph
- Higher architectural complexity
- Less predictable long-running workflows

---

## Enterprise Readiness

Medium

---

## Long-Term Viability

High

---

## Decision

Experimental

AutoGen MAY be evaluated for future autonomous collaborative agent scenarios.

It SHALL NOT be part of the initial Approved Stack for production orchestration.

---

# 15. CrewAI Evaluation

## Purpose

Framework for collaborative role-based AI agents.

---

## Advantages

- Simple conceptual model
- Fast development
- Readable workflows
- Good educational material
- Active community

---

## Weaknesses

- Higher abstraction level
- Less control over execution lifecycle
- Smaller enterprise adoption
- Limited deterministic orchestration
- Overlaps significantly with LangGraph capabilities

---

## Enterprise Readiness

Medium

---

## Long-Term Viability

Medium

---

## Decision

Rejected

CrewAI is not approved for JARVIS Core because LangGraph provides greater architectural flexibility, stronger state management, better recovery mechanisms, and superior long-term scalability.

---

# 16. DSPy Evaluation

## Purpose

Optimization framework for prompts and language model pipelines.

---

## Advantages

- Automatic prompt optimization
- Declarative programming model
- Research-backed methodology
- Rapid experimentation
- Potential quality improvements

---

## Weaknesses

- Limited production adoption
- Rapid evolution
- Specialized use cases
- Additional architectural complexity

---

## Enterprise Readiness

Medium

---

## Long-Term Viability

Promising

---

## Decision

Experimental

DSPy MAY be evaluated in future optimization workflows but SHALL NOT become a foundational dependency of JARVIS v1.

---

# 17. Guidance Evaluation

## Purpose

Framework for constrained generation and deterministic prompt construction.

---

## Advantages

- Precise control over generation
- Strong structured prompting
- Deterministic execution
- Useful for specialized workflows

---

## Weaknesses

- Smaller ecosystem
- Narrow scope
- Limited orchestration capabilities
- Reduced enterprise adoption

---

## Enterprise Readiness

Medium

---

## Decision

Rejected

Structured generation requirements are sufficiently addressed by PydanticAI together with native provider capabilities.

Introducing Guidance would increase dependency complexity without proportional architectural benefit.

---

# 18. Technical Comparison

| Framework | Maturity | Enterprise | Multi Provider | Tool Calling | Structured Output | Workflow | Decision |
|-----------|----------|------------|----------------|--------------|-------------------|----------|----------|
| LangChain | Excellent | Excellent | Excellent | Excellent | Good | Good | Approved |
| LangGraph | Excellent | Excellent | Excellent | Excellent | Excellent | Excellent | Approved |
| PydanticAI | High | High | Excellent | Excellent | Excellent | Moderate | Approved |
| LlamaIndex | High | High | Good | Good | Good | Good | Conditionally Approved |
| Haystack | High | High | Good | Moderate | Moderate | Good | Experimental |
| Semantic Kernel | High | Excellent | Moderate | Good | Good | Good | Conditionally Approved |
| AutoGen | Medium | Medium | Good | Good | Moderate | Good | Experimental |
| CrewAI | Medium | Medium | Good | Moderate | Moderate | Moderate | Rejected |
| DSPy | Medium | Medium | Good | Limited | Moderate | Moderate | Experimental |
| Guidance | Medium | Medium | Limited | Limited | Good | Limited | Rejected |

---

# 19. Performance Assessment

Evaluation considered:

- Runtime latency
- Streaming overhead
- Memory consumption
- Context management
- Parallel execution
- Tool execution latency
- Agent orchestration efficiency

Results:

## LangGraph

Excellent

Optimized for durable execution and complex workflows.

---

## LangChain

Excellent

Large abstraction layer with acceptable overhead.

---

## PydanticAI

Excellent

Minimal overhead with efficient validation.

---

## LlamaIndex

High

Performance depends on retrieval backend.

---

## Haystack

High

Optimized for enterprise search infrastructure.

---

## AutoGen

Moderate

Conversation loops increase runtime costs.

---

## CrewAI

Moderate

Simplified orchestration introduces unnecessary abstraction layers.

---

# 20. Scalability Assessment

Scalability requirements include:

- Thousands of workflows
- Long-running execution
- Horizontal scaling
- Distributed workers
- Stateful recovery
- Cloud-native deployment

Evaluation:

| Framework | Scalability |
|------------|-------------|
| LangGraph | Excellent |
| LangChain | Excellent |
| PydanticAI | Excellent |
| LlamaIndex | High |
| Haystack | High |
| Semantic Kernel | High |
| AutoGen | Medium |
| CrewAI | Medium |
| DSPy | Medium |
| Guidance | Low |

---

# 21. Reliability Assessment

Reliability considers:

- Stable APIs
- Backward compatibility
- Predictable execution
- Error recovery
- Failure isolation
- Recovery mechanisms

Approved frameworks demonstrated significantly higher operational reliability than experimental alternatives.

---

# 22. Maintainability Assessment

Maintainability criteria include:

- Documentation quality
- API consistency
- Upgrade difficulty
- Community support
- Long-term maintenance outlook

Approved technologies showed the lowest expected maintenance cost over the projected 5–10 year architectural horizon.

---

# 23. Security Assessment

The approved AI framework stack SHALL satisfy the following security requirements:

- Secure API handling
- Credential isolation
- Provider abstraction
- Prompt injection mitigation support
- Output validation
- Tool execution isolation
- Dependency auditing
- Version verification
- Supply chain monitoring

Frameworks lacking mature security practices SHALL not be approved.

---

# 24. License Review

| Framework | License | Commercial Use |
|------------|---------|----------------|
| LangChain | MIT | Approved |
| LangGraph | MIT | Approved |
| PydanticAI | MIT | Approved |
| LlamaIndex | MIT | Approved |
| Haystack | Apache-2.0 | Approved |
| Semantic Kernel | MIT | Approved |
| AutoGen | MIT | Approved |
| CrewAI | MIT | Approved |
| DSPy | MIT | Approved |
| Guidance | MIT | Approved |

All evaluated licenses are compatible with commercial JARVIS development.

---

# 25. Community Assessment

Evaluation considered:

- GitHub activity
- Maintainer responsiveness
- Documentation quality
- Contributor diversity
- Enterprise adoption
- Educational resources

LangChain and LangGraph currently represent the strongest overall ecosystems.

---

# 26. Integration with JAS

Approved AI frameworks SHALL integrate with:

- Kernel
- Agent Architecture
- Memory Layer
- Plugin Layer
- Browser Layer
- Voice Layer
- Vision Layer
- MCP Layer
- Security Layer
- Planning Layer

No framework SHALL bypass architectural boundaries defined by JAS.

---

# 27. Bootstrap Considerations

Bootstrap SHALL automatically install:

- LangChain
- LangGraph
- PydanticAI

Optional components such as LlamaIndex SHALL be installed only when enabled by Manifest.

Experimental frameworks SHALL never be installed by default.

---

# 28. Manifest Representation

Manifest SHALL define:

- Framework name
- Approved version
- Installation source
- Dependency group
- Optional status
- Required providers
- Compatibility constraints

Framework configuration SHALL remain independent from runtime model configuration.

---

# 29. Version Lock Strategy

Every approved framework SHALL be pinned within Version Lock.

Version updates SHALL require:

- Compatibility validation
- Regression testing
- Security review
- Architecture compliance verification

Automatic major-version upgrades SHALL be prohibited.

---

# 30. Decision

The official JARVIS AI framework architecture is approved as follows.

Primary orchestration:

- LangGraph

Primary ecosystem:

- LangChain

Primary structured output framework:

- PydanticAI

Conditional frameworks:

- LlamaIndex
- Semantic Kernel

Experimental frameworks:

- Haystack
- AutoGen
- DSPy

Rejected frameworks:

- CrewAI
- Guidance

---

# 31. Approved Technologies

- LangGraph
- LangChain
- PydanticAI

Conditionally Approved:

- LlamaIndex
- Semantic Kernel

Experimental:

- Haystack
- AutoGen
- DSPy

---

# 32. Rejected Technologies

- CrewAI
- Guidance

Rejected technologies remain documented for historical traceability and future reassessment.

---

# 33. Future Re-Evaluation Policy

Future revisions SHALL consider:

- New framework maturity
- Breaking architectural improvements
- Security posture
- Enterprise adoption
- Performance evolution
- AI ecosystem shifts
- Standardization efforts
- Long-context innovations
- Native multimodal capabilities

Re-evaluation SHALL occur only during major Approved Stack revisions.

---

# 34. Dependencies

This document depends upon:

- Approved Stack Overview
- Stack Governance and Selection Policy
- Core Runtime and Programming Languages

This document SHALL serve as an input for:

- Version Lock
- Manifest
- Bootstrap
- Architecture Compliance Checker
- Agent Orchestration Stack
- Approved Models

---

# Revision History

| Version | Description |
|----------|-------------|
| 0.1 | Initial framework evaluation draft |
| 0.5 | Added candidate comparison and evaluation methodology |
| 0.8 | Added enterprise assessment, performance, security, and integration sections |
| 1.0 | Approved AI and LLM Frameworks Architecture |

---

# End of Document